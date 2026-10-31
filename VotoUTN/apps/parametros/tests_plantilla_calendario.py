from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.notificaciones.models import PlantillaNotificacion
from apps.parametros.models import FechaAdministrativa


class PlantillaDesdeFechaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="editor", password="prueba")
        self.client.force_login(self.usuario)
        self.url = reverse("crear-plantilla-calendario")
        self.datos = {
            "nueva-nombre": "Aviso personalizado", "nueva-codigo": "aviso-personalizado",
            "nueva-asunto": "Aviso de {nombre_eleccion}",
            "nueva-contenido": "Hola {nombre_destinatario}",
            "nueva-roles_destinatarios": ["elector"],
        }

    def test_crea_audita_y_permite_seleccionar_en_fecha(self):
        respuesta = self.client.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 201)
        plantilla = PlantillaNotificacion.objects.get(pk=respuesta.json()["plantilla"]["id"])
        self.assertEqual(plantilla.categoria, "calendario")
        self.assertFalse(plantilla.permite_envio_manual)
        self.assertTrue(plantilla.activa)
        self.assertTrue(EventoAuditoria.objects.filter(entidad=plantilla._meta.label, entidad_id=plantilla.pk).exists())
        respuesta = self.client.post(reverse("crear-parametro", args=("fechas-administrativas",)), {
            "codigo": "fecha", "nombre": "Fecha", "estado_eleccion": "publicada",
            "envia_mensaje": "on", "plantilla_mensaje": plantilla.pk,
            "roles_destinatarios": ["elector"], "alcance_todos_claustros": "on",
            "criterio_destinatarios": "todos_en_alcance", "activa": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(FechaAdministrativa.objects.get().plantilla_mensaje, plantilla)

    def test_rechaza_variables_invalidas_y_duplicados_sin_guardar(self):
        self.datos["nueva-contenido"] = "Hola {variable_invalida}"
        respuesta = self.client.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("contenido", respuesta.json()["errores"])
        self.assertFalse(PlantillaNotificacion.objects.exists())
        self.datos["nueva-contenido"] = "Hola"
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 201)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 400)
        self.assertEqual(PlantillaNotificacion.objects.count(), 1)

    def test_exige_permiso_y_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        usuario = get_user_model().objects.create_user(username="sin-permiso")
        self.client.force_login(usuario)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 403)
        self.assertFalse(PlantillaNotificacion.objects.exists())

    def test_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(self.url, self.datos).status_code, 403)
        self.assertFalse(PlantillaNotificacion.objects.exists())

    def test_error_de_fecha_preserva_datos_y_editor(self):
        respuesta = self.client.post(reverse("crear-parametro", args=("fechas-administrativas",)), {
            "nombre": "Conservar este borrador", "envia_mensaje": "on",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "parametros/fecha_formulario.html")
        self.assertContains(respuesta, "Conservar este borrador")
        self.assertContains(respuesta, 'id="crear-plantilla-dialogo"')
        self.assertIn("plantilla_mensaje", respuesta.context["formulario"].errors)
        self.assertFalse(FechaAdministrativa.objects.exists())
