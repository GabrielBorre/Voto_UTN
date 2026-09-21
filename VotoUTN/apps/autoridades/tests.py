from datetime import datetime, timedelta

from django.contrib.auth import get_user_model, login
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, RequestFactory, TestCase
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
from apps.usuarios.backend_auth import ElectorBackend, ElectorUser
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
        self.assertIn("40123456,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar", contenido)


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
        self.elector = Elector.objects.create(legajo="2024001", nombre="Juan", dni="40123456", correo_electronico="juan@frba.utn.edu.ar")
        self.registro = RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

    def test_validar_csv_autoridades_acepta_formato_nuevo(self):
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,2024001,Juan,Perez,K,juan@frba.utn.edu.ar\n"

        filas, errores = validar_csv_autoridades(contenido, self.eleccion)

        self.assertEqual(errores, [])
        self.assertEqual(filas[0]["dni"], "40123456")
        self.assertEqual(filas[0]["legajo"], "2024001")

    def test_validar_csv_autoridades_acepta_alias_mail_mayusculas(self):
        contenido = b"DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail\n40123456,2024001,Juan,Perez,K,juan@frba.utn.edu.ar\n"

        filas, errores = validar_csv_autoridades(contenido, self.eleccion)

        self.assertEqual(errores, [])
        self.assertEqual(len(filas), 1)


class ElectorBackendTests(TestCase):
    def test_elector_virtual_no_se_guarda_en_auth_user(self):
        usuario = ElectorBackend().authenticate(None, dni="40111222", username="eva", first_name="Eva")

        self.assertIsInstance(usuario, ElectorUser)
        self.assertTrue(usuario.is_authenticated)
        self.assertEqual(usuario.username, "eva")
        self.assertFalse(get_user_model().objects.filter(username="40111222").exists())

    def test_login_elector_guarda_id_entero_en_sesion(self):
        usuario = ElectorBackend().authenticate(None, dni="28111333", username="alumnocg", first_name="Alumno")
        request = RequestFactory().get("/")
        request.session = SessionStore()

        login(request, usuario, backend="apps.usuarios.backend_auth.ElectorBackend")

        self.assertEqual(request.session["_auth_user_id"], "28111333")
        self.assertEqual(request.session["_auth_user_backend"], "apps.usuarios.backend_auth.ElectorBackend")

    def test_get_user_elector_virtual_reconstruye_sin_elector_en_bd(self):
        usuario = ElectorBackend().get_user("38999222")

        self.assertIsNotNone(usuario)
        self.assertTrue(getattr(usuario, "is_authenticated", False))
        self.assertTrue(getattr(usuario, "es_elector", False))
        self.assertEqual(usuario.dni, "38999222")

    def test_login_elector_virtual_se_rehidrata_en_la_siguiente_peticion(self):
        cliente = Client()
        usuario = ElectorBackend().authenticate(None, dni="28111333", first_name="Alumno")
        request = RequestFactory().get("/")
        request.session = SessionStore()
        login(request, usuario, backend="apps.usuarios.backend_auth.ElectorBackend")
        request.session["keycloak_user"] = {
            "dni": "28111333",
            "username": "alumnocg",
            "first_name": "Alumno",
            "last_name": "CG",
            "email": "alumno@example.com",
            "subject": "kc-sub",
        }
        request.session.save()
        cliente.cookies["sessionid"] = request.session.session_key

        respuesta = cliente.get(reverse("index"), HTTP_HOST="localhost")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.wsgi_request.user.is_authenticated)
        self.assertEqual(respuesta.wsgi_request.user.dni, "28111333")
        self.assertEqual(respuesta.wsgi_request.user.username, "alumnocg")
        self.assertEqual(respuesta.wsgi_request.user.first_name, "Alumno")
        self.assertEqual(respuesta.wsgi_request.user.last_name, "CG")
        self.assertEqual(respuesta.wsgi_request.user.email, "alumno@example.com")
