from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.usuarios.backend_auth import ElectorUser


class InicioAutenticadoTests(TestCase):
    def test_login_redirige_al_flujo_oidc_de_keycloak(self):
        respuesta = self.client.get(reverse("keycloak_login"), HTTP_HOST="localhost:8000")

        self.assertEqual(respuesta.status_code, 302)
        destino = urlparse(respuesta.url)
        parametros = parse_qs(destino.query)
        self.assertEqual(destino.path, "/realms/FRBA/protocol/openid-connect/auth")
        self.assertEqual(parametros["client_id"], ["VOTOUTN"])
        self.assertEqual(parametros["response_type"], ["code"])
        self.assertEqual(parametros["redirect_uri"], ["http://localhost:8000/callback"])

    def test_seccion_protegida_redirige_al_login_configurado(self):
        destino = reverse("gestionar-partidos", args=(4,))

        respuesta = self.client.get(destino)

        self.assertRedirects(
            respuesta,
            f"{reverse('keycloak_login')}?next={destino}",
            fetch_redirect_response=False,
        )

    def test_superusuario_ingresa_al_panel_de_gestion(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-prueba",
            password="clave-prueba",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertRedirects(
            respuesta,
            reverse("gestionar-elecciones"),
            fetch_redirect_response=False,
        )

    def test_usuario_operativo_ingresa_a_la_seleccion_de_eleccion(self):
        usuario = get_user_model().objects.create_user(
            username="operador-prueba",
            password="clave-prueba",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertRedirects(
            respuesta,
            reverse("lista-elecciones"),
            fetch_redirect_response=False,
        )

    def test_usuario_autenticado_ve_menu_compartido_con_enlace_a_inicio(self):
        usuario = get_user_model().objects.create_user(
            username="usuario-menu",
            password="clave-prueba",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(respuesta, 'aria-label="Navegación de Junta Electoral"')
        self.assertContains(respuesta, f'href="{reverse("inicio-autenticado")}"')

    def test_elector_keycloak_puede_abrir_su_inicio(self):
        elector = ElectorUser("9876543210")
        self.client.force_login(elector, backend="apps.usuarios.backend_auth.ElectorBackend")

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Mi información electoral")
