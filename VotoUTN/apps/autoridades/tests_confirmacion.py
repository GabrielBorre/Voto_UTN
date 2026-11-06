from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades import tests as base
from apps.autoridades.confirmacion import confirmar_autoridades
from apps.autoridades.distribucion import distribuir
from apps.autoridades.models import ConfiguracionAutoridades
from apps.autoridades.seleccion_manual import asignar_manualmente
from apps.autoridades.services import asignar_autoridad
from apps.elecciones.models import Eleccion
from apps.notificaciones.models import EnvioNotificacion
from apps.padron.models import SolicitudCambioSede


class ConfirmacionAutoridadesTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        asignar_autoridad(self.registros[0], self.mesa, self.manana, self.usuario)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(
            estado=Eleccion.Estado.PUBLICADA, fecha_cierre_solicitudes_cambio_sede=timezone.localdate() - timedelta(days=1),
        )
        self.eleccion.refresh_from_db()

    def test_autoridades_son_editables_en_publicada_antes_del_cierre(self):
        self.client.force_login(self.usuario)
        url = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        respuesta = self.client.get(url)
        self.assertFalse(respuesta.context["configuracion_solo_lectura"])
        respuesta = self.client.post(url, {"guardar-turnos": "", "configuracion-turnos": [self.manana.pk], f"titulares_{self.manana.pk}": "2", f"minimo_titulares_{self.manana.pk}": "1"})
        self.assertEqual(respuesta.status_code, 302)
        asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="titular")

    def test_sorteo_se_puede_calcular_en_publicada(self):
        ConfiguracionAutoridades.objects.create(eleccion_claustro=self.eleccion_claustro, modo="aleatorio")
        distribuir(self.eleccion_claustro, self.usuario)

    def test_exige_resolver_solicitudes_y_fin_de_plazo(self):
        limite = timezone.localdate() + timedelta(days=3)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(fecha_cierre_solicitudes_cambio_sede=timezone.localdate())
        with self.assertRaisesMessage(ValidationError, "plazo"):
            confirmar_autoridades(self.eleccion.pk, self.usuario, limite)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(fecha_cierre_solicitudes_cambio_sede=timezone.localdate() - timedelta(days=1))
        SolicitudCambioSede.objects.create(registro_padron=self.registros[1], sede_origen=self.sede_votacion, sede_destino=self.sede)
        with self.assertRaisesMessage(ValidationError, "solicitudes"):
            confirmar_autoridades(self.eleccion.pk, self.usuario, limite)
        self.assertFalse(EnvioNotificacion.objects.filter(plantilla__codigo="autoridad-convocatoria-definitiva").exists())

    def test_no_confirma_si_hay_electores_sin_mesa(self):
        from apps.mesas.models import AsignacionMesa
        AsignacionMesa.objects.filter(registro_padron=self.registros[2]).delete()
        with self.assertRaisesMessage(ValidationError, "electores activos deben tener mesa"):
            confirmar_autoridades(self.eleccion.pk, self.usuario, timezone.localdate() + timedelta(days=1))

    def test_no_inicia_si_hay_electores_sin_mesa(self):
        from apps.mesas.models import AsignacionMesa
        AsignacionMesa.objects.filter(registro_padron=self.registros[2]).delete()
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        self.eleccion.refresh_from_db()
        with patch.object(Eleccion, "validar_configuracion"):
            with self.assertRaisesMessage(ValidationError, "electores activos deben tener una mesa"):
                self.eleccion.cambiar_estado(Eleccion.Estado.EN_CURSO)

    def test_no_inicia_si_mesa_no_alcanza_minimo(self):
        self.eleccion_claustro.turnos_autoridad.update(minimo_titulares_por_mesa=2)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        self.eleccion.refresh_from_db()
        with patch.object(Eleccion, "validar_configuracion"):
            with self.assertRaisesMessage(ValidationError, "no alcanza el mínimo de autoridades"):
                self.eleccion.cambiar_estado(Eleccion.Estado.EN_CURSO)

    def test_confirma_una_vez_convoca_y_bloquea_ediciones(self):
        limite = timezone.localdate() + timedelta(days=3)
        with patch("apps.notificaciones.services.enviar_notificacion") as enviar:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(confirmar_autoridades(self.eleccion.pk, self.usuario, limite), 1)
            enviar.assert_called_once()
        self.eleccion.refresh_from_db()
        self.assertTrue(self.eleccion.autoridades_confirmadas_en)
        self.assertEqual(self.eleccion.fecha_limite_justificacion_autoridades, limite)
        self.assertEqual(EnvioNotificacion.objects.filter(plantilla__codigo="autoridad-convocatoria-definitiva").count(), 1)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk)))
        self.assertFalse(respuesta.context["configuracion_solo_lectura"])
        self.assertContains(respuesta, "Autoridades confirmadas")
        self.assertNotContains(respuesta, ">Editar mesa</a>")
        with self.assertRaises(ValidationError):
            confirmar_autoridades(self.eleccion.pk, self.usuario, limite)
        with self.assertRaises(PermissionDenied):
            asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="titular")
