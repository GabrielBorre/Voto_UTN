from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.parametros.models import Sede


class ParametrosViewsTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="admin", password="clave")

    def test_gestionar_parametros_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-parametros"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "elecciones/parametros.html")

    def test_listar_parametros_usa_ruta_publica_existente(self):
        Sede.objects.create(nombre="Campus")
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("listar-parametros", args=("sedes",)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "elecciones/parametro_lista.html")
