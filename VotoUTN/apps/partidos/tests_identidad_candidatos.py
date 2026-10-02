from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.elecciones.models import EleccionClaustroDepartamento
from apps.padron.models import RegistroPadron
from apps.parametros.models import Departamento
from apps.partidos.forms import FormularioCandidato
from apps.partidos.models import Candidato, ImportacionCandidaturas
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
        return previsualizar_candidatos_lista(participacion=self.participacion, usuario=self.usuario,
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
        self.assertEqual(confirmar_candidatos_lista(importacion, self.participacion), 1)
        self.assertEqual(Candidato.objects.get().elector, self.elector)

    def test_csv_cuil_previsualiza_y_confirma(self):
        self.elector.tipo_documento, self.elector.dni = "CUIL", "20301112223"
        self.elector.save()
        importacion = self.preview("CUIL", "20-30111222-3")
        self.assertEqual(importacion.errores, [])
        confirmar_candidatos_lista(importacion, self.participacion)
        self.assertEqual(Candidato.objects.get().dni, self.elector.dni)

    def test_csv_revalida_tipo_documento_al_confirmar(self):
        importacion = self.preview("DNI", self.elector.dni)
        self.assertEqual(importacion.errores, [])
        self.elector.tipo_documento = "CUIL"
        self.elector.save()
        with self.assertRaises(ValidationError):
            confirmar_candidatos_lista(importacion, self.participacion)
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
