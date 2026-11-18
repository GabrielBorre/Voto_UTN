import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede


class ConsultaPadronApiTests(TestCase):
    def setUp(self):
        inicio = timezone.now()
        self.eleccion = Eleccion.objects.create(
            nombre="Elección activa",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            habilitada=True,
            estado=Eleccion.Estado.EN_CURSO,
        )
        claustro = Claustro.objects.create(nombre="Estudiantes")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.sede = Sede.objects.create(nombre="Campus")
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=claustro,
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=departamento,
        )
        elector = Elector.objects.create(
            dni="40123456",
            legajo="2024001",
            nombre="Ana",
            apellido="Pérez",
        )
        self.registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

    def consultar(self, codigo):
        return self.client.post(
            reverse("api-consulta-padron"),
            data=json.dumps({"codigo": codigo}),
            content_type="application/json",
        )

    def test_consulta_por_dni_devuelve_datos_del_padron_y_mesa(self):
        mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            numero=12,
        )
        AsignacionSedePadron.objects.create(
            registro_padron=self.registro,
            sede=self.sede,
            estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=mesa)

        respuesta = self.consultar("40123456")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.json(),
            {
                "claustro": "Estudiantes",
                "nombre": "Ana",
                "apellido": "Pérez",
                "dni": "40123456",
                "sede": "Campus",
                "especialidad": "Sistemas",
                "mesa": "K-012",
            },
        )

    def test_consulta_por_legajo_funciona_y_muestra_mesa_no_asignada(self):
        respuesta = self.consultar("2024001")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["mesa"], "Sin asignar")

    def test_consulta_por_dni_funciona_en_eleccion_publicada(self):
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.save(update_fields=("estado",))
        self.registro.sede = None
        self.registro.save(update_fields=("sede",))
        AsignacionSedePadron.objects.create(
            registro_padron=self.registro,
            sede=self.sede,
            estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        mesa = Mesa.objects.create(eleccion=self.eleccion, numero=12)
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=mesa)

        respuesta = self.consultar("40123456")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["nombre"], "Ana")
        self.assertEqual(respuesta.json()["sede"], "Campus")
        self.assertEqual(
            respuesta.json()["mesa"],
            "Se informará próximamente.",
        )

    def test_consulta_usa_sede_de_mesa_si_no_hay_asignacion_de_sede(self):
        sede_electoral = Sede.objects.create(nombre="Medrano")
        self.registro.sede = None
        self.registro.save(update_fields=("sede",))
        mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=13,
            sede=sede_electoral,
        )
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=mesa)

        respuesta = self.consultar("40123456")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["sede"], "Medrano")

    def test_consulta_sin_codigo_es_rechazada(self):
        respuesta = self.client.post(
            reverse("api-consulta-padron"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 400)

    def test_consulta_no_expone_padrones_de_elecciones_no_abiertas(self):
        self.eleccion.estado = Eleccion.Estado.FINALIZADA
        self.eleccion.save(update_fields=("estado",))

        respuesta = self.consultar("40123456")

        self.assertEqual(respuesta.status_code, 404)