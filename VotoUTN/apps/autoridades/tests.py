from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.autoridades.services import validar_csv_autoridades
from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
)
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede
from apps.usuarios.models import AsignacionRol


class AutoridadesViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)

    def test_gestionar_autoridades_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-autoridades", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "autoridades/gestion.html")

    def test_mis_asignaciones_autoridad_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("mis-asignaciones-autoridad"))

        self.assertEqual(respuesta.status_code, 403)

    def test_descargar_plantilla_autoridades_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("descargar-plantilla-autoridades", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        contenido = respuesta.content.decode("utf-8-sig")
        self.assertIn("DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail", contenido)
        self.assertIn("40123456,2024001,Juan,Perez,K,juan.perez@utn.edu.ar", contenido)


class AutoridadesImportTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.sede = Sede.objects.create(nombre="Campus")
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.elector = Elector.objects.create(legajo="2024001", nombre="Juan", dni="40123456", correo_electronico="juan@test.com")
        self.registro = RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

    def test_validar_csv_autoridades_acepta_formato_nuevo(self):
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,2024001,Juan,Perez,K,juan@test.com\n"

        filas, errores = validar_csv_autoridades(contenido, self.eleccion)

        self.assertEqual(errores, [])
        self.assertEqual(filas[0]["dni"], "40123456")
        self.assertEqual(filas[0]["legajo"], "2024001")

    def test_validar_csv_autoridades_acepta_alias_mail_mayusculas(self):
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,2024001,Juan,Perez,K,juan@test.com\n"

        filas, errores = validar_csv_autoridades(contenido, self.eleccion)

        self.assertEqual(errores, [])
        self.assertEqual(len(filas), 1)
