from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ImportacionCandidaturas,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    Partido,
    PuestoEleccion,
)
from apps.partidos.forms import FormularioPuestoEleccion


class PartidosBaseTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 9, 10, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion de prueba",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes"),
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="SIS"),
        )
        self.partido = Partido.objects.create(nombre="Frente Universitario", sigla="FU")
        self.participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            partido=self.partido,
            codigo_presentacion="EST-10",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="10",
            nombre_lista="Universidad Abierta",
        )
        self.organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        self.puesto = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Consejero/a",
            permite_filtrar_departamentos=True,
        )
        self.puesto_eleccion = PuestoEleccion.objects.create(
            puesto=self.puesto,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            cantidad_titulares=3,
            cantidad_suplentes=3,
        )
        self.lista = ListaCandidatos.objects.create(
            participacion=self.participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Consejo Departamental",
            puesto_eleccion=self.puesto_eleccion,
        )


class CandidatoTests(PartidosBaseTests):
    def test_lista_rechaza_un_claustro_de_otra_eleccion(self):
        inicio = make_aware(datetime(2026, 9, 12, 8))
        otra_eleccion = Eleccion.objects.create(
            nombre="Otra eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        otro_alcance = EleccionClaustro.objects.create(
            eleccion=otra_eleccion,
            claustro=self.eleccion_claustro.claustro,
        )
        lista = ListaCandidatos(
            participacion=self.participacion,
            eleccion_claustro=otro_alcance,
            nombre="Alcance invalido",
        )

        with self.assertRaises(ValidationError):
            lista.full_clean()

    def test_candidato_puede_no_pertenecer_al_padron(self):
        candidato = Candidato(
            lista=self.lista,
            nombre="Persona Independiente",
            dni="30111222",
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        candidato.full_clean()
        candidato.save()

        self.assertIsNone(candidato.elector_id)

    def test_candidato_puede_vincularse_a_elector_sin_registro_en_el_padron(self):
        elector = Elector.objects.create(legajo="100", nombre="Maria Electoral", dni="30222333")
        candidato = Candidato(
            lista=self.lista,
            elector=elector,
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        candidato.full_clean()
        candidato.save()

        self.assertEqual(candidato.nombre, elector.nombre)
        self.assertEqual(candidato.dni, elector.dni)

    def test_elector_en_padron_de_otro_claustro_no_puede_integrar_la_lista(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        otra_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_claustro,
            departamento=Departamento.objects.create(nombre="Civil", codigo="CIV"),
        )
        elector = Elector.objects.create(legajo="101", nombre="Otro Elector", dni="30333444")
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=otra_configuracion,
        )
        candidato = Candidato(
            lista=self.lista,
            elector=elector,
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        with self.assertRaises(ValidationError):
            candidato.full_clean()

    def test_una_persona_puede_integrar_mas_de_una_candidatura_en_la_eleccion(self):
        Candidato.objects.create(
            lista=self.lista,
            nombre="Persona Repetida",
            dni="30444555",
            cargo="Consejero",
            orden=1,
        )
        segundo_partido = Partido.objects.create(nombre="Espacio Academico")
        segunda_participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            partido=segundo_partido,
            codigo_presentacion="EST-20",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="20",
        )
        segunda_lista = ListaCandidatos.objects.create(
            participacion=segunda_participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Lista Alternativa",
        )
        duplicado = Candidato(
            lista=segunda_lista,
            nombre="Persona Repetida",
            dni="30444555",
            cargo="Consejero",
            orden=1,
        )

        duplicado.full_clean()
        duplicado.save()
        self.assertEqual(Candidato.objects.filter(dni="30444555").count(), 2)

    def test_candidato_rechaza_orden_superior_al_puesto_configurado(self):
        candidato = Candidato(
            lista=self.lista,
            nombre="Persona fuera de orden",
            identificador_persona="LEGAJO-99",
            tipo=Candidato.Tipo.TITULAR,
            orden=4,
        )

        with self.assertRaises(ValidationError):
            candidato.full_clean()


class PartidosViewsTests(PartidosBaseTests):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username="admin-partidos", password="clave")
        self.client.login(username="admin-partidos", password="clave")

    def test_panel_requiere_permiso_y_usa_template_propietario(self):
        respuesta = self.client.get(reverse("gestionar-partidos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "partidos/gestion.html")

        sin_permiso = get_user_model().objects.create_user(username="sin-permiso")
        self.client.force_login(sin_permiso)
        respuesta = self.client.get(reverse("gestionar-partidos", args=(self.eleccion.id,)))
        self.assertEqual(respuesta.status_code, 403)

    def test_admite_numero_repetido_en_presentaciones_independientes(self):
        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "crear_presentacion",
                "presentacion-codigo_presentacion": "EST-OTRA-10",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": self.participacion.numero_lista,
                "presentacion-nombre_lista": "Número repetido permitido",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            ParticipacionPartido.objects.filter(eleccion=self.eleccion, numero_lista="10").count(),
            2,
        )

    def test_desactiva_candidato_mediante_post(self):
        candidato = Candidato.objects.create(
            lista=self.lista,
            nombre="Candidato activo",
            dni="30777666",
            cargo="Consejero",
            orden=1,
        )

        respuesta = self.client.post(
            reverse("cambiar-estado-candidato", args=(self.eleccion.id, candidato.id)),
            {"activo": "0"},
        )

        candidato.refresh_from_db()
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(candidato.activo)

    def test_flujo_crea_presentacion_lista_y_candidato_independiente(self):
        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "crear_presentacion",
                "presentacion-codigo_presentacion": "EST-30",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "30",
                "presentacion-nombre_lista": "Innovación",
                "presentacion-apoderado_nombre": "Ana Apoderada",
                "presentacion-apoderado_email": "ana@example.com",
            },
        )
        participacion = ParticipacionPartido.objects.get(codigo_presentacion="EST-30", eleccion=self.eleccion)
        self.assertEqual(respuesta.status_code, 302)

        respuesta = self.client.post(
            reverse("detalle-participacion-partido", args=(self.eleccion.id, participacion.id)),
            {
                "puesto_eleccion": self.puesto_eleccion.id,
            },
        )
        lista = ListaCandidatos.objects.get(participacion=participacion)
        self.assertEqual(respuesta.status_code, 302)

        respuesta = self.client.post(
            reverse("detalle-lista-candidatos", args=(self.eleccion.id, lista.id)),
            {
                "dni_elector": "",
                "identificador_persona": "NRO-30",
                "nombre": "Candidata Externa",
                "dni": "30999888",
                "correo_electronico": "externa@example.com",
                "tipo": Candidato.Tipo.TITULAR,
                "orden": 1,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Candidato.objects.filter(lista=lista, dni="30999888", elector__isnull=True).exists())

    def test_puesto_sin_alcance_departamental_rechaza_departamento(self):
        puesto_general = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante general",
            permite_filtrar_departamentos=False,
        )
        formulario = FormularioPuestoEleccion(
            data={
                "puesto": puesto_general.pk,
                "tipo_alcance": FormularioPuestoEleccion.TIPO_DEPARTAMENTO,
                "eleccion_claustro": self.eleccion_claustro.pk,
                "eleccion_claustro_departamento": self.configuracion.pk,
                "cantidad_titulares": 1,
                "cantidad_suplentes": 0,
                "activo": "on",
            },
            eleccion=self.eleccion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("eleccion_claustro_departamento", formulario.errors)

    def test_habilita_multiples_claustros_y_departamentos_en_una_operacion(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        claustro_graduado = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        departamento_docente = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_docente,
            departamento=Departamento.objects.create(nombre="Industrial", codigo="IND"),
        )
        departamento_graduado = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_graduado,
            departamento=Departamento.objects.create(nombre="Electrónica", codigo="ELE"),
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": self.puesto.pk,
                "puesto-limitar_por_claustros": "on",
                "puesto-claustros": [claustro_docente.pk, claustro_graduado.pk],
                "puesto-limitar_por_departamentos": "on",
                "puesto-departamentos": [
                    departamento_docente.departamento_id,
                    departamento_graduado.departamento_id,
                ],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(claustro_docente, claustro_graduado),
                eleccion_claustro_departamento__isnull=False,
            ).count(),
            2,
        )
        self.assertFalse(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(claustro_docente, claustro_graduado),
                eleccion_claustro_departamento__isnull=True,
            ).exists()
        )

    def test_sin_limite_departamental_crea_un_alcance_por_cada_claustro(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        claustro_nodocente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="No Docentes"),
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": self.puesto.pk,
                "puesto-limitar_por_claustros": "on",
                "puesto-claustros": [claustro_docente.pk, claustro_nodocente.pk],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(claustro_docente, claustro_nodocente),
                eleccion_claustro_departamento__isnull=True,
            ).count(),
            2,
        )

    def test_sin_filtros_habilita_todos_los_claustros(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": self.puesto.pk,
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(self.eleccion_claustro, claustro_docente),
                eleccion_claustro_departamento__isnull=True,
            ).count(),
            2,
        )

    def test_filtro_departamental_no_exige_activar_filtro_por_claustros(self):
        puesto_departamental = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante departamental",
            permite_filtrar_claustros=False,
            permite_filtrar_departamentos=True,
        )
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_docente,
            departamento=self.configuracion.departamento,
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": puesto_departamental.pk,
                "puesto-limitar_por_departamentos": "on",
                "puesto-departamentos": [self.configuracion.departamento_id],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 0,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=puesto_departamental,
                eleccion_claustro_departamento__departamento=self.configuracion.departamento,
            ).count(),
            2,
        )

    def test_csv_previsualiza_advierte_y_confirma_presentaciones_independientes(self):
        contenido = "\n".join(
            (
                "codigo_presentacion;numero_lista;nombre_lista;apoderado_nombre;apoderado_email;claustro;organo;puesto;departamento;identificador_persona;dni;apellido;nombres;tipo_candidatura;orden",
                "EST-A;3;Integracion;Ana Apoderada;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;LEGAJO-1;;Perez;Maria;titular;1",
                "EST-B;3;Otra Integracion;Bruno Apoderado;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;LEGAJO-1;;Perez;Maria;titular;1",
            )
        )
        archivo = SimpleUploadedFile("candidaturas.csv", contenido.encode("utf-8"), content_type="text/csv")

        respuesta = self.client.post(
            reverse("importar-candidaturas", args=(self.eleccion.pk,)),
            {"archivo": archivo},
        )

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="candidaturas.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertEqual(importacion.cantidad_valida, 2)
        self.assertEqual(len(importacion.advertencias), 1)
        self.assertContains(respuesta, "requiere revisi")

        respuesta = self.client.post(
            reverse("confirmar-importacion-candidaturas", args=(self.eleccion.pk, importacion.pk)),
        )

        self.assertEqual(respuesta.status_code, 302)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.CONFIRMADA)
        self.assertEqual(
            ParticipacionPartido.objects.filter(eleccion=self.eleccion, numero_lista="3").count(),
            2,
        )
        self.assertEqual(Candidato.objects.filter(identificador_persona="LEGAJO-1").count(), 2)

    def test_csv_rechaza_orden_superior_a_la_cantidad_configurada(self):
        contenido = "\n".join(
            (
                "codigo_presentacion;numero_lista;nombre_lista;apoderado_nombre;apoderado_email;claustro;organo;puesto;departamento;identificador_persona;dni;apellido;nombres;tipo_candidatura;orden",
                "EST-A;3;Integracion;Ana Apoderada;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;LEGAJO-9;;Perez;Maria;titular;4",
            )
        )
        archivo = SimpleUploadedFile("orden-invalido.csv", contenido.encode("utf-8"), content_type="text/csv")

        respuesta = self.client.post(
            reverse("importar-candidaturas", args=(self.eleccion.pk,)),
            {"archivo": archivo},
        )

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="orden-invalido.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertEqual(importacion.cantidad_valida, 0)
        self.assertTrue(any("supera" in error for error in importacion.errores))
