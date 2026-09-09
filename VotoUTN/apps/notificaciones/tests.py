from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
