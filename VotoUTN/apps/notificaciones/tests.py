from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.notificaciones.forms import FormularioEnviarNotificacion
from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.notificaciones.services import crear_envios, notificaciones_para_usuario, procesar_envios_pendientes
from apps.padron.models import Elector
from apps.parametros.models import FechaAdministrativa
from apps.usuarios.backend_auth import ElectorUser
from apps.usuarios.models import PerfilUsuario


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
            contenido="Elección: {nombre_eleccion}. Justificativo de {tipo_ausencia}.",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
        )
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("previsualizar-plantilla", args=(plantilla.pk,)))

        self.assertContains(respuesta, "Hola María Pérez")
        self.assertContains(respuesta, "Elección: Elección UTN")
        self.assertContains(respuesta, "Justificativo de ausencia a votar.")
        self.assertEqual(plantilla.envios.count(), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificacionesDestinatariosTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="destinatario", email="local@example.test")
        self.elector = Elector.objects.create(
            legajo="4001", dni="40123456", nombre="Ana", apellido="Pérez",
            correo_electronico="elector@example.test",
        )
        self.plantilla = PlantillaNotificacion.objects.create(
            codigo="aviso", nombre="Aviso", asunto="Mensaje recibido", contenido="Contenido original.",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
        )
        self.envio = EnvioNotificacion.objects.create(
            plantilla=self.plantilla, elector=self.elector,
            asunto=self.plantilla.asunto, contenido=self.plantilla.contenido,
        )

    def ingresar_como_elector(self):
        self.client.force_login(
            ElectorUser(self.elector.dni),
            backend="apps.usuarios.backend_auth.ElectorBackend",
        )

    def test_elector_keycloak_sin_usuario_local_ve_su_notificacion_y_contador(self):
        self.ingresar_como_elector()

        respuesta = self.client.get(reverse("mis-notificaciones"))

        self.assertContains(respuesta, self.envio.asunto)
        self.assertEqual(list(respuesta.context["notificaciones"]), [self.envio])
        self.assertEqual(respuesta.context["notificaciones_no_leidas"], 1)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_usuario_con_perfil_de_elector_ve_la_misma_notificacion(self):
        PerfilUsuario.objects.create(usuario=self.usuario, elector=self.elector)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("mis-notificaciones"))

        self.assertEqual(list(respuesta.context["notificaciones"]), [self.envio])
        self.assertEqual(respuesta.context["notificaciones_no_leidas"], 1)

    def test_leer_conserva_el_contenido_original_y_fecha_de_primera_lectura(self):
        self.ingresar_como_elector()
        url = reverse("leer-notificacion", args=(self.envio.pk,))
        self.plantilla.contenido = "Contenido modificado de la plantilla."
        self.plantilla.save(update_fields=("contenido",))

        respuesta = self.client.get(url)

        self.assertContains(respuesta, "Contenido original.")
        self.assertNotContains(respuesta, self.plantilla.contenido)
        self.envio.refresh_from_db()
        primera_lectura = self.envio.leida_en
        self.assertIsNotNone(primera_lectura)
        self.client.get(url)
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.leida_en, primera_lectura)
        listado = self.client.get(reverse("mis-notificaciones"))
        self.assertEqual(listado.context["notificaciones_no_leidas"], 0)

    def test_otro_usuario_no_puede_listar_ni_leer_notificaciones_ajenas(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("mis-notificaciones"))
        detalle = self.client.get(reverse("leer-notificacion", args=(self.envio.pk,)))

        self.assertEqual(list(respuesta.context["notificaciones"]), [])
        self.assertEqual(respuesta.context["notificaciones_no_leidas"], 0)
        self.assertEqual(detalle.status_code, 404)
        self.envio.refresh_from_db()
        self.assertIsNone(self.envio.leida_en)

    def test_otro_elector_keycloak_no_puede_leer_notificaciones_ajenas(self):
        Elector.objects.create(legajo="4002", dni="40123457", nombre="Otro elector")
        self.client.force_login(
            ElectorUser("40123457"),
            backend="apps.usuarios.backend_auth.ElectorBackend",
        )

        respuesta = self.client.get(reverse("mis-notificaciones"))
        detalle = self.client.get(reverse("leer-notificacion", args=(self.envio.pk,)))

        self.assertEqual(list(respuesta.context["notificaciones"]), [])
        self.assertEqual(respuesta.context["notificaciones_no_leidas"], 0)
        self.assertEqual(detalle.status_code, 404)

    def test_elector_no_accede_a_usuario_local_con_pk_igual_a_su_dni(self):
        envio_local = EnvioNotificacion.objects.create(
            plantilla=self.plantilla, destinatario=self.usuario, asunto="Privado", contenido="Mensaje local.",
        )

        notificaciones = notificaciones_para_usuario(ElectorUser(str(self.usuario.pk)))

        self.assertNotIn(envio_local, notificaciones)

    def test_notificaciones_existentes_de_usuario_local_siguen_visibles(self):
        PerfilUsuario.objects.create(usuario=self.usuario, elector=self.elector)
        envio_local = EnvioNotificacion.objects.create(
            plantilla=self.plantilla, destinatario=self.usuario, asunto="Anterior", contenido="Mensaje anterior.",
        )
        self.ingresar_como_elector()

        respuesta = self.client.get(reverse("mis-notificaciones"))

        self.assertEqual(set(respuesta.context["notificaciones"]), {self.envio, envio_local})

    def test_base_de_datos_rechaza_notificaciones_sin_destinatario(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            EnvioNotificacion.objects.create(plantilla=self.plantilla, asunto="Sin destinatario", contenido="Inválido.")

    def test_procesador_envia_a_elector_y_usuario_con_el_contenido_guardado(self):
        EnvioNotificacion.objects.create(
            plantilla=self.plantilla, destinatario=self.usuario, asunto="Local", contenido="Mensaje local.",
        )

        self.assertEqual(procesar_envios_pendientes(), 2)

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual({correo.to[0] for correo in mail.outbox}, {"local@example.test", "elector@example.test"})
        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioNotificacion.Estado.ENVIADO)
        self.assertEqual(procesar_envios_pendientes(), 0)

    def test_fallo_de_correo_conserva_notificacion_interna_y_registra_error(self):
        with patch("apps.notificaciones.services.send_mail", side_effect=SMTPException("fallo simulado")):
            with self.assertLogs("apps.notificaciones.services", level="WARNING"):
                procesar_envios_pendientes()

        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioNotificacion.Estado.ERROR)
        self.assertIsNone(self.envio.enviada_en)
        self.assertEqual(self.envio.error, "No se pudo enviar el correo.")
        self.ingresar_como_elector()
        self.assertContains(self.client.get(reverse("mis-notificaciones")), self.envio.asunto)

    def test_sin_correo_no_se_marca_como_enviado(self):
        self.elector.correo_electronico = ""
        self.elector.save(update_fields=("correo_electronico",))

        with self.assertLogs("apps.notificaciones.services", level="WARNING"):
            procesar_envios_pendientes()

        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioNotificacion.Estado.ERROR)
        self.assertIsNone(self.envio.enviada_en)
        self.assertEqual(self.envio.error, "El destinatario no tiene correo electrónico.")

    def test_proveedor_sin_confirmacion_no_se_marca_como_enviado(self):
        with patch("apps.notificaciones.services.send_mail", return_value=0):
            with self.assertLogs("apps.notificaciones.services", level="WARNING"):
                procesar_envios_pendientes()

        self.envio.refresh_from_db()
        self.assertEqual(self.envio.estado, EnvioNotificacion.Estado.ERROR)
        self.assertIsNone(self.envio.enviada_en)
        self.assertEqual(self.envio.error, "El proveedor no confirmó el envío del correo.")
