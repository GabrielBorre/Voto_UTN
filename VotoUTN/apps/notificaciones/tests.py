from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.notificaciones.forms import FormularioEnviarNotificacion
from apps.notificaciones.models import PlantillaNotificacion
from apps.notificaciones.services import crear_envios
from apps.parametros.models import FechaAdministrativa


class NotificacionesViewsTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="admin", password="clave")

    def test_gestionar_notificaciones_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-notificaciones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "notificaciones/gestion.html")

    def test_mis_notificaciones_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("mis-notificaciones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "notificaciones/mis_notificaciones.html")

    def test_envio_manual_oculta_plantillas_automaticas(self):
        manual = PlantillaNotificacion.objects.create(
            codigo="manual", nombre="Manual", asunto="Aviso", contenido="Contenido",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
            permite_envio_manual=True,
        )
        automatica = PlantillaNotificacion.objects.create(
            codigo="automatica", nombre="Automática", asunto="Aviso", contenido="Contenido",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
            permite_envio_manual=False,
        )

        formulario = FormularioEnviarNotificacion()

        self.assertIn(manual, formulario.fields["plantilla"].queryset)
        self.assertNotIn(automatica, formulario.fields["plantilla"].queryset)
        with self.assertRaises(ValueError):
            crear_envios(automatica)

    def test_catalogo_permite_previsualizar_sin_generar_envios(self):
        plantilla = PlantillaNotificacion.objects.create(
            codigo="vista", nombre="Vista", asunto="Hola {nombre_destinatario}",
            contenido="Elección: {nombre_eleccion}",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
        )
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("previsualizar-plantilla", args=(plantilla.pk,)))

        self.assertContains(respuesta, "Hola María Pérez")
        self.assertContains(respuesta, "Elección: Elección UTN")
        self.assertEqual(plantilla.envios.count(), 0)
