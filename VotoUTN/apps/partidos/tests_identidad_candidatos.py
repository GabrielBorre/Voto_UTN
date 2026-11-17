from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.elecciones.models import EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.partidos.forms import FormularioCandidato
from apps.partidos.models import Candidato, CargoElectivo, ImportacionCandidaturas, ListaCandidatos, PuestoEleccion
from apps.partidos.services import (
    buscar_elector_candidato, confirmar_candidatos_lista,
    confirmar_importacion_candidaturas, previsualizar_candidatos_lista,
    previsualizar_importacion_candidaturas,
)
from apps.partidos.tests import PartidosBaseTests


class IdentidadCandidatoTests(PartidosBaseTests):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username="identidad-admin", password="prueba")
        self.client.force_login(self.usuario)
        self.elector = self.crear_elector_padron(dni="30111222", legajo="UTN-010")
        self.url_busqueda = reverse("buscar-elector-candidato", args=(self.eleccion.pk, self.lista.pk))

    def buscar(self, tipo, documento):
        return buscar_elector_candidato(eleccion=self.eleccion, puesto=self.puesto_eleccion,
                                       tipo_documento=tipo, documento=documento)

    def archivo(self, filas):
        return SimpleUploadedFile("candidatos.csv", "\n".join(filas).encode("utf-8"), content_type="text/csv")

    def preview(self, tipo, documento):
        return previsualizar_candidatos_lista(lista=self.lista, usuario=self.usuario,
            archivo=self.archivo([
                "organo;puesto;departamento;tipo_documento;documento;tipo_candidatura;orden",
                f"Consejo Departamental;Consejero/a;Sistemas;{tipo};{documento};titular;1",
            ]))

    def test_dni_y_legajo_identifican_al_mismo_elector(self):
        self.assertEqual(self.buscar("DNI", "30.111.222"), self.elector)
        self.assertEqual(self.buscar("LEGAJO", "UTN-010"), self.elector)
        with self.assertRaises(ValidationError):
            self.buscar("LEGAJO", self.elector.dni)
        with self.assertRaises(ValidationError):
            self.buscar("DNI", self.elector.legajo)

    def test_cuil_exige_tipo_del_padron_y_no_deriva_desde_dni(self):
        with self.assertRaises(ValidationError):
            self.buscar("CUIL", self.elector.dni)
        self.elector.tipo_documento = "CUIL"
        self.elector.dni = "20301112223"
        self.elector.save()
        self.assertEqual(self.buscar("cuil", "20-30111222-3"), self.elector)
        self.assertEqual(self.buscar("LEGAJO", self.elector.legajo), self.elector)
        with self.assertRaises(ValidationError):
            self.buscar("DNI", self.elector.dni)

    def test_rechaza_tipo_invalido_y_valores_vacios(self):
        for tipo, documento in [("PASAPORTE", "30111222"), ("", "30111222"), ("DNI", ""), ("DNI", "abc"), ("DNI", "1" * 13)]:
            with self.subTest(tipo=tipo, documento=documento), self.assertRaises(ValidationError):
                self.buscar(tipo, documento)

    def test_padron_debe_estar_activo_y_ser_de_la_eleccion(self):
        registro = RegistroPadron.objects.get(elector=self.elector)
        registro.activo = False
        registro.save()
        with self.assertRaises(ValidationError):
            self.buscar("LEGAJO", self.elector.legajo)
        registro.delete()
        with self.assertRaises(ValidationError):
            self.buscar("DNI", self.elector.dni)

    def test_controla_departamento_y_permite_puestos_generales(self):
        otra_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Civil", codigo="CIV-ID"),
        )
        RegistroPadron.objects.filter(elector=self.elector).update(eleccion_claustro_departamento=otra_configuracion)
        with self.assertRaisesMessage(ValidationError, "otro departamento"):
            self.buscar("LEGAJO", self.elector.legajo)
        self.puesto_eleccion.eleccion_claustro_departamento = None
        self.assertEqual(self.buscar("LEGAJO", self.elector.legajo), self.elector)

    def test_rechaza_registro_de_otro_claustro_aunque_coincida_el_departamento(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Otro claustro"),
        )
        otro_alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_claustro, departamento=self.configuracion.departamento,
        )
        RegistroPadron.objects.filter(elector=self.elector).update(eleccion_claustro_departamento=otro_alcance)
        with self.assertRaisesMessage(ValidationError, "otro claustro"):
            self.buscar("DNI", self.elector.dni)
        candidato = Candidato(lista=self.lista, elector=self.elector, tipo="titular", orden=1)
        with self.assertRaisesMessage(ValidationError, "otro claustro"):
            candidato.full_clean()

    def test_formulario_por_legajo_toma_nombre_del_padron_ignora_nombre_enviado(self):
        formulario = FormularioCandidato({"tipo_documento": "LEGAJO", "documento": self.elector.legajo,
            "nombre_padron": "Nombre falso", "tipo": "titular", "orden": 1}, lista=self.lista)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        candidato = formulario.save()
        self.assertEqual(candidato.elector, self.elector)
        self.assertEqual(candidato.nombre, self.elector.nombre_completo)
        self.assertEqual(candidato.dni, self.elector.dni)

    def test_edicion_invalida_no_conserva_elector_anterior(self):
        candidato = Candidato(lista=self.lista, elector=self.elector, cargo="Consejero/a", tipo="titular", orden=1)
        candidato.full_clean()
        candidato.save()
        formulario = FormularioCandidato({"tipo_documento": "DNI", "documento": "99999999",
            "tipo": "titular", "orden": 1}, instance=candidato, lista=self.lista)
        self.assertFalse(formulario.is_valid())
        self.assertIn("documento", formulario.errors)
        candidato.refresh_from_db()
        self.assertEqual(candidato.elector, self.elector)

    def test_mismo_elector_no_se_duplica_en_un_puesto_con_otro_orden(self):
        candidato = Candidato(lista=self.lista, elector=self.elector, cargo="Consejero/a", tipo="titular", orden=1)
        candidato.full_clean()
        candidato.save()
        formulario = FormularioCandidato({"tipo_documento": "LEGAJO", "documento": self.elector.legajo,
            "tipo": "suplente", "orden": 2}, lista=self.lista)
        self.assertFalse(formulario.is_valid())

    def test_edicion_de_cuil_inicializa_tipo_numero_y_nombre(self):
        self.elector.tipo_documento, self.elector.dni = "CUIL", "20301112223"
        self.elector.save()
        candidato = Candidato(lista=self.lista, elector=self.elector, cargo="Consejero/a", tipo="titular", orden=1)
        candidato.full_clean()
        candidato.save()
        formulario = FormularioCandidato(instance=candidato, lista=self.lista)
        self.assertEqual(formulario["tipo_documento"].value(), "CUIL")
        self.assertEqual(formulario["documento"].value(), self.elector.dni)
        self.assertEqual(formulario["nombre_padron"].value(), self.elector.nombre_completo)

    def test_consulta_muestra_solo_nombre_sin_guardar_y_sin_cache(self):
        respuesta = self.client.post(self.url_busqueda, {"tipo_documento": "LEGAJO", "documento": self.elector.legajo})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"nombre": self.elector.nombre_completo})
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertFalse(Candidato.objects.exists())
        self.assertEqual(self.client.get(self.url_busqueda).status_code, 405)

    def test_consulta_exige_permiso_y_csrf_y_limita_eleccion(self):
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.force_login(self.usuario)
        self.assertEqual(cliente_csrf.post(self.url_busqueda, {"tipo_documento": "DNI", "documento": self.elector.dni}).status_code, 403)
        sin_permiso = get_user_model().objects.create_user(username="identidad-sin-permiso")
        self.client.force_login(sin_permiso)
        self.assertEqual(self.client.post(self.url_busqueda).status_code, 403)
        self.client.force_login(self.usuario)
        otra_url = reverse("buscar-elector-candidato", args=(self.eleccion.pk + 100, self.lista.pk))
        self.assertEqual(self.client.post(otra_url).status_code, 404)

    def test_consulta_rechaza_documento_de_otro_tipo(self):
        respuesta = self.client.post(self.url_busqueda, {"tipo_documento": "CUIL", "documento": self.elector.dni})
        self.assertEqual(respuesta.status_code, 400)
        self.assertNotIn("nombre", respuesta.json())

    def test_csv_legajo_previsualiza_y_confirma(self):
        importacion = self.preview("LEGAJO", self.elector.legajo)
        self.assertEqual(importacion.errores, [])
        self.assertEqual(importacion.filas[0]["nombre"], self.elector.nombre_completo)
        self.assertEqual(confirmar_candidatos_lista(importacion, self.lista), 1)
        self.assertEqual(Candidato.objects.get().elector, self.elector)

    def test_csv_cuil_previsualiza_y_confirma(self):
        self.elector.tipo_documento, self.elector.dni = "CUIL", "20301112223"
        self.elector.save()
        importacion = self.preview("CUIL", "20-30111222-3")
        self.assertEqual(importacion.errores, [])
        confirmar_candidatos_lista(importacion, self.lista)
        self.assertEqual(Candidato.objects.get().dni, self.elector.dni)

    def test_csv_revalida_tipo_documento_al_confirmar(self):
        importacion = self.preview("DNI", self.elector.dni)
        self.assertEqual(importacion.errores, [])
        self.elector.tipo_documento = "CUIL"
        self.elector.save()
        with self.assertRaises(ValidationError):
            confirmar_candidatos_lista(importacion, self.lista)
        self.assertFalse(Candidato.objects.exists())
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)

    def test_csv_general_usa_mismo_resolvedor_por_legajo(self):
        importacion = previsualizar_importacion_candidaturas(eleccion=self.eleccion, usuario=self.usuario,
            archivo=self.archivo([
                "codigo_presentacion;numero_lista;nombre_lista;apoderado_nombre;claustro;organo;puesto;departamento;tipo_documento;documento;tipo_candidatura;orden",
                f"EST-20;20;Lista veinte;Apoderada;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;LEGAJO;{self.elector.legajo};titular;1",
            ]))
        self.assertEqual(importacion.errores, [])
        confirmar_importacion_candidaturas(importacion)
        self.assertEqual(Candidato.objects.get().elector, self.elector)

    def test_csv_con_documento_vacio_o_tipo_invalido_rechaza(self):
        for tipo, documento in [("", self.elector.dni), ("PASAPORTE", self.elector.dni), ("DNI", "")]:
            with self.subTest(tipo=tipo, documento=documento):
                importacion = self.preview(tipo, documento)
                self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)


class CandidatosMultipuestoTests(PartidosBaseTests):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username="multipuesto-admin")
        self.client.force_login(self.usuario)
        self.url = reverse("detalle-participacion-partido", args=(self.eleccion.pk, self.participacion.pk))
        cargo = CargoElectivo.objects.create(organo=self.organo, nombre="Consejero general")
        cargo.claustros_habilitados.add(self.eleccion_claustro.claustro)
        self.general = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=2, cantidad_suplentes=2,
        )
        self.lista_general = ListaCandidatos.objects.create(
            participacion=self.participacion, eleccion_claustro=self.eleccion_claustro,
            nombre="General", puesto_eleccion=self.general,
        )
        self.elector = self.crear_elector_padron(dni="30111222")

    def previsualizar(self, *filas):
        contenido = "\n".join((
            "puesto;departamento;tipo_documento;documento;tipo_candidatura;orden",
            *filas,
        ))
        respuesta = self.client.post(self.url, {
            "accion": "previsualizar_multipuesto",
            "multipuesto-archivo": SimpleUploadedFile("multipuesto.csv", contenido.encode("utf-8")),
        })
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.context["importacion_multipuesto"]

    def confirmar(self, importacion):
        return self.client.post(self.url, {
            "accion": "confirmar_multipuesto", "importacion_id": importacion.pk,
        })

    def test_solo_muestra_y_acepta_puestos_asociados_a_la_lista(self):
        self.lista_general.delete()
        otra = self.participacion.__class__.objects.create(
            eleccion=self.eleccion, eleccion_claustro=self.eleccion_claustro,
            numero_lista="99", codigo_presentacion="OTRA",
        )
        ListaCandidatos.objects.create(
            participacion=otra, eleccion_claustro=self.eleccion_claustro,
            nombre="General", puesto_eleccion=self.general,
        )
        pantalla = self.client.get(self.url)
        disponibles = list(pantalla.context["puestos_multipuesto_disponibles"])
        self.assertIn(self.puesto_eleccion, disponibles)
        self.assertNotIn(self.general, disponibles)
        self.assertNotContains(pantalla, "General (departamento vacío)")

        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertFalse(Candidato.objects.exists())

    def test_puesto_inactivo_no_se_muestra_ni_se_acepta(self):
        self.lista_general.activa = False
        self.lista_general.save(update_fields=("activa",))
        pantalla = self.client.get(self.url)
        self.assertNotIn(self.general, pantalla.context["puestos_multipuesto_disponibles"])
        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)

    def test_no_reasocia_puesto_eliminado_tras_previsualizar(self):
        importacion = self.previsualizar(f"Consejero/a;Sistemas;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.errores, [])
        self.lista.delete()

        respuesta = self.confirmar(importacion)
        self.assertRedirects(respuesta, f"{self.url}#importar-multipuesto")
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(ListaCandidatos.objects.filter(puesto_eleccion=self.puesto_eleccion).exists())
        self.assertFalse(Candidato.objects.exists())

    def test_plantilla_de_puesto_general_sanitiza_y_se_puede_importar(self):
        self.general.puesto.nombre = "=Consejero general"
        self.general.puesto.save(update_fields=("nombre",))
        lista = self.lista_general
        plantilla = self.client.get(
            reverse("plantilla-candidatos-lista", args=(self.eleccion.pk, self.participacion.pk)),
            {"puesto": lista.pk},
        )
        contenido = plantilla.content.decode("utf-8-sig")
        self.assertIn("'=Consejero general;;DNI;;titular;1", contenido)
        contenido = contenido.replace("DNI;;titular;1", f"DNI;{self.elector.dni};titular;1", 1)
        respuesta = self.client.post(
            f"{self.url}?puesto={lista.pk}&pestana_candidatos=csv",
            {
                "accion": "previsualizar_candidatos",
                "archivo": SimpleUploadedFile("puesto.csv", contenido.encode("utf-8")),
            },
        )
        importacion = respuesta.context["importacion"]
        self.assertEqual(importacion.errores, [])
        self.assertEqual(confirmar_candidatos_lista(importacion, lista), 1)
        self.assertTrue(Candidato.objects.filter(lista=lista, elector=self.elector).exists())

    def test_importa_varios_puestos_asociados_sin_seleccionarlos(self):
        pantalla = self.client.get(self.url)
        self.assertNotContains(pantalla, 'name="multipuesto-puestos_seleccionados"')
        self.assertContains(pantalla, "Indicá en cada fila un puesto activo ya asociado a esta lista")
        self.assertContains(pantalla, "Consejero general")
        self.assertContains(pantalla, "Consejero general — General")
        self.assertNotContains(pantalla, "General (departamento vacío)")

        plantilla = self.client.get(
            reverse("plantilla-candidatos-lista", args=(self.eleccion.pk, self.participacion.pk)),
            {"formato": "multipuesto"},
        )
        self.assertEqual(
            plantilla.content.decode("utf-8-sig").strip(),
            "puesto;departamento;tipo_documento;documento;tipo_candidatura;orden",
        )
        importacion = self.previsualizar(
            f"Consejero/a;Sistemas;DNI;{self.elector.dni};titular;1",
            f"Consejero general;;LEGAJO;{self.elector.legajo};titular;1",
        )
        self.assertEqual(importacion.errores, [])
        self.assertEqual(importacion.cantidad_valida, 2)
        respuesta = self.confirmar(importacion)
        self.assertRedirects(respuesta, f"{self.url}#importar-multipuesto")
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.CONFIRMADA)
        self.assertEqual(Candidato.objects.filter(elector=self.elector).count(), 2)
        self.assertTrue(ListaCandidatos.objects.filter(
            participacion=self.participacion, puesto_eleccion=self.general,
        ).exists())

    def test_rechaza_puesto_habilitado_solo_para_otro_claustro(self):
        otro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Docentes"),
        )
        cargo = CargoElectivo.objects.create(organo=self.organo, nombre="Exclusivo docentes")
        cargo.claustros_habilitados.add(otro.claustro)
        PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=otro, cantidad_titulares=1, cantidad_suplentes=1,
        )

        self.assertNotContains(self.client.get(self.url), "Exclusivo docentes")
        importacion = self.previsualizar(f"Exclusivo docentes;;DNI;{self.elector.dni};titular;1")

        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertIn("no identifican un único puesto habilitado", importacion.errores[0])
        self.assertFalse(Candidato.objects.exists())

    def test_rechaza_csv_sin_columna_puesto(self):
        archivo = SimpleUploadedFile(
            "candidatos.csv",
            f"departamento;tipo_documento;documento;tipo_candidatura;orden\n"
            f"Sistemas;DNI;{self.elector.dni};titular;1".encode("utf-8"),
        )
        respuesta = self.client.post(self.url, {
            "accion": "previsualizar_multipuesto", "multipuesto-archivo": archivo,
        })

        importacion = respuesta.context["importacion_multipuesto"]
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertIn("puesto", importacion.errores[0])
        self.assertFalse(Candidato.objects.exists())

    def test_rechaza_importacion_en_lista_sin_puestos(self):
        self.lista.delete()
        self.lista_general.delete()
        pantalla = self.client.get(self.url)
        self.assertContains(pantalla, "No hay puestos activos asociados a esta lista.")
        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertFalse(Candidato.objects.exists())

    def test_importa_el_mismo_puesto_en_dos_departamentos(self):
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Civil", codigo="CIV-M"),
        )
        puesto_civil = PuestoEleccion.objects.create(
            puesto=self.puesto, eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=alcance, cantidad_titulares=1, cantidad_suplentes=1,
        )
        ListaCandidatos.objects.create(
            participacion=self.participacion, eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=alcance, nombre="Civil", puesto_eleccion=puesto_civil,
        )
        otro = self.crear_elector_padron(dni="30111223", configuracion=alcance)
        importacion = self.previsualizar(
            f"Consejero/a;Sistemas;DNI;{self.elector.dni};titular;1",
            f"Consejero/a;Civil;DNI;{otro.dni};titular;1",
        )
        self.assertEqual(importacion.errores, [])
        self.confirmar(importacion)
        self.assertTrue(Candidato.objects.filter(lista__puesto_eleccion=puesto_civil, elector=otro).exists())
        self.assertTrue(Candidato.objects.filter(lista=self.lista, elector=self.elector).exists())

    def test_rechaza_puesto_desconocido_ambiguo_o_departamento_incorrecto(self):
        otro_cargo = CargoElectivo.objects.create(
            organo=self.organo, nombre="consejero general",
        )
        otro_cargo.claustros_habilitados.add(self.eleccion_claustro.claustro)
        otro_puesto = PuestoEleccion.objects.create(
            puesto=otro_cargo, eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1, cantidad_suplentes=1,
        )
        ListaCandidatos.objects.create(
            participacion=self.participacion, eleccion_claustro=self.eleccion_claustro,
            nombre="Otro general", puesto_eleccion=otro_puesto,
        )
        for puesto, departamento in (
            ("Inexistente", ""), ("Consejero general", ""),
            ("Consejero/a", ""), ("Consejero/a", "Otro"),
        ):
            with self.subTest(puesto=puesto, departamento=departamento):
                importacion = self.previsualizar(
                    f"{puesto};{departamento};DNI;{self.elector.dni};titular;1",
                )
                self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertFalse(Candidato.objects.exists())

    def test_rechaza_ocupados_repetidos_y_candidatos_fuera_del_padron(self):
        Candidato.objects.create(
            lista=self.lista, elector=self.elector, dni=self.elector.dni,
            cargo=self.puesto.nombre, tipo="titular", orden=1,
        )
        for filas in (
            (f"Consejero/a;Sistemas;DNI;{self.elector.dni};titular;1",),
            (f"Consejero/a;Sistemas;DNI;{self.elector.dni};suplente;2",),
            ("Consejero general;;DNI;99999999;titular;1",),
            (f"Consejero general;;DNI;{self.elector.dni};titular;1",) * 2,
        ):
            with self.subTest(filas=filas):
                importacion = self.previsualizar(*filas)
                self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertEqual(Candidato.objects.count(), 1)

    def test_cambio_despues_de_previsualizar_revierte_todo(self):
        importacion = self.previsualizar(
            f"Consejero general;;DNI;{self.elector.dni};titular;1",
            f"Consejero/a;Sistemas;DNI;{self.elector.dni};titular;1",
        )
        self.assertEqual(importacion.errores, [])
        Candidato.objects.create(
            lista=self.lista, nombre="Candidato existente", dni="30999999",
            cargo=self.puesto.nombre, tipo="titular", orden=1,
        )
        self.confirmar(importacion)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertTrue(ListaCandidatos.objects.filter(puesto_eleccion=self.general).exists())
        self.assertFalse(Candidato.objects.filter(lista=self.lista_general).exists())
        self.assertEqual(Candidato.objects.count(), 1)

    def test_revalida_puesto_y_no_permite_confirmar_en_otra_lista(self):
        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.general.activo = False
        self.general.save(update_fields=("activo",))
        self.confirmar(importacion)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(Candidato.objects.exists())
        otra = self.participacion.__class__.objects.create(
            eleccion=self.eleccion, eleccion_claustro=self.eleccion_claustro,
            numero_lista="99", codigo_presentacion="OTRA",
        )
        respuesta = self.client.post(
            reverse("detalle-participacion-partido", args=(self.eleccion.pk, otra.pk)),
            {"accion": "confirmar_multipuesto", "importacion_id": importacion.pk},
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Candidato.objects.exists())

    def test_rechaza_si_cambia_el_alcance_tras_previsualizar(self):
        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.errores, [])
        self.general.eleccion_claustro_departamento = self.configuracion
        self.general.save(update_fields=("eleccion_claustro_departamento",))
        self.confirmar(importacion)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(Candidato.objects.exists())

    def test_rechaza_si_el_puesto_deja_de_admitir_el_claustro(self):
        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.errores, [])
        self.general.puesto.claustros_habilitados.clear()
        self.confirmar(importacion)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(Candidato.objects.exists())
        importacion = self.previsualizar(f"Consejero general;;DNI;{self.elector.dni};titular;1")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)

    def test_sin_permiso_no_importa(self):
        self.client.force_login(get_user_model().objects.create_user(username="sin-permiso-multipuesto"))
        respuesta = self.client.post(self.url, {"accion": "confirmar_multipuesto", "importacion_id": 1})
        self.assertEqual(respuesta.status_code, 403)
