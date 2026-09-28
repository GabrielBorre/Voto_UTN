from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.usuarios.backend_auth import ElectorUser


class InicioAutenticadoTests(TestCase):
    def test_login_sin_destino_explicito_redirige_al_inicio_por_rol(self):
        get_user_model().objects.create_superuser(
            username="admin-login",
            password="clave-prueba",
        )

        respuesta = self.client.post(
            reverse("login"),
            {"username": "admin-login", "password": "clave-prueba"},
        )

        self.assertRedirects(
            respuesta,
            reverse("inicio-autenticado"),
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
