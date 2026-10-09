from datetime import date
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.elecciones.models import Eleccion
from apps.usuarios.backend_auth import ElectorUser
from apps.usuarios.models import AsignacionRol


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

    def test_lista_muestra_aviso_si_no_hay_eleccion_en_curso(self):
        usuario = get_user_model().objects.create_user(
            username="operador-sin-eleccion",
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
        )
        Eleccion.objects.create(
            nombre="Elección cerrada",
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 2),
            estado=Eleccion.Estado.CERRADA,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(
            respuesta,
            "Debe haber una elección en curso para poder registrar participación.",
        )
        self.assertContains(respuesta, "Elecciones y asistencia")
        self.assertContains(
            respuesta,
            'class="gestion-nav__disabled" role="link" aria-disabled="true" tabindex="0" title="Debe haber una elección en curso para poder registrar participación."',
        )
        self.assertNotContains(
            respuesta,
            f'href="{reverse("lista-elecciones")}"',
        )

    def test_lista_muestra_aviso_sin_titulo_seleccion_si_hay_eleccion_en_curso_pero_no_hay_opciones(self):
        usuario = get_user_model().objects.create_user(
            username="operador-sin-opciones",
        )
        self.client.force_login(usuario)
        Eleccion.objects.create(
            nombre="Elección abierta",
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 2),
            estado=Eleccion.Estado.ABIERTA,
        )

        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(
            respuesta,
            "La elección todavía no está abierta para poder registrar participación.",
        )
        self.assertNotContains(respuesta, "Seleccioná una elección")
        self.assertNotContains(respuesta, 'href="/escanear/')

    def test_lista_considera_en_curso_borrador_preparada_y_abierta(self):
        usuario = get_user_model().objects.create_user(
            username="operador-con-eleccion",
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
        )
        self.client.force_login(usuario)

        for estado in (
            Eleccion.Estado.BORRADOR,
            Eleccion.Estado.PREPARADA,
            Eleccion.Estado.ABIERTA,
        ):
            with self.subTest(estado=estado):
                eleccion = Eleccion.objects.create(
                    nombre=f"Elección {estado}",
                    fecha_inicio=date(2026, 10, 1),
                    fecha_fin=date(2026, 10, 2),
                    estado=estado,
                )

                respuesta = self.client.get(reverse("lista-elecciones"))

                self.assertNotContains(
                    respuesta,
                    "Debe haber una elección en curso para poder registrar participación.",
                )
                self.assertContains(
                    respuesta,
                    f'href="{reverse("lista-elecciones")}"',
                )
                self.assertNotContains(respuesta, 'class="gestion-nav__disabled"')
                eleccion.delete()

    def test_elector_keycloak_puede_abrir_su_inicio(self):
        elector = ElectorUser("9876543210")
        self.client.force_login(elector, backend="apps.usuarios.backend_auth.ElectorBackend")

        respuesta = self.client.get(reverse("inicio-autenticado"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Mi información electoral")
