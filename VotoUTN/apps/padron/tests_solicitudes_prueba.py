from io import StringIO
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades import tests as base
from apps.elecciones.models import Eleccion
from apps.padron.models import AsignacionSedePadron, SolicitudCambioSede
from apps.padron.services import calcular_asignaciones_sede_claustro, resolver_solicitud_cambio_sede


class SolicitudesPruebaTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.PUBLICADA, fecha_cierre_solicitudes_cambio_sede=timezone.localdate() + timedelta(days=1))

    def test_simula_y_crea_solicitudes_sin_aprobarlas(self):
        salida = StringIO()
        call_command("generar_solicitudes_prueba", eleccion=self.eleccion.pk, stdout=salida)
        self.assertIn("Simulación", salida.getvalue())
        self.assertFalse(SolicitudCambioSede.objects.exists())
        call_command("generar_solicitudes_prueba", eleccion=self.eleccion.pk, aplicar=True, stdout=StringIO())
        solicitud = SolicitudCambioSede.objects.get()
        self.assertEqual(solicitud.estado, SolicitudCambioSede.Estado.PENDIENTE)
        self.assertEqual(solicitud.sede_origen, self.sede_votacion)
        self.assertEqual(solicitud.sede_destino, self.sede)

    def test_cierre_de_prueba_simula_y_luego_aplica(self):
        fecha = (timezone.localdate() + timedelta(days=2)).isoformat()
        original = Eleccion.objects.get(pk=self.eleccion.pk).fecha_cierre_solicitudes_cambio_sede
        call_command("cerrar_plazo_cambio_sede_prueba", eleccion=self.eleccion.pk, fecha=fecha, stdout=StringIO())
        self.assertEqual(Eleccion.objects.get(pk=self.eleccion.pk).fecha_cierre_solicitudes_cambio_sede, original)
        call_command("cerrar_plazo_cambio_sede_prueba", eleccion=self.eleccion.pk, fecha=fecha, aplicar=True, stdout=StringIO())
        self.assertEqual(Eleccion.objects.get(pk=self.eleccion.pk).fecha_cierre_solicitudes_cambio_sede.isoformat(), fecha)

    def test_cierre_de_prueba_no_modifica_autoridades_confirmadas(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(autoridades_confirmadas_en=timezone.now())
        with self.assertRaises(CommandError):
            call_command("cerrar_plazo_cambio_sede_prueba", eleccion=self.eleccion.pk, aplicar=True, stdout=StringIO())

    def test_aprobar_cambia_sede_electoral_sin_modificar_sede_de_cursada(self):
        registro = self.registros[0]
        registro.sede = None
        registro.save(update_fields=("sede",))
        solicitud = SolicitudCambioSede.objects.create(registro_padron=registro, sede_origen=self.sede_votacion, sede_destino=self.sede)
        resolver_solicitud_cambio_sede(solicitud, "aprobada", self.usuario)
        registro.refresh_from_db()
        self.assertIsNone(registro.sede)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede, self.sede)
        calcular_asignaciones_sede_claustro(self.eleccion_claustro)
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede, self.sede)

    def test_aprobacion_masiva_muestra_movimientos_y_solo_aplica_tras_confirmacion(self):
        solicitud = SolicitudCambioSede.objects.create(registro_padron=self.registros[0], sede_origen=self.sede_votacion, sede_destino=self.sede)
        self.client.force_login(self.usuario)
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        respuesta = self.client.post(url, {"accion": "aprobar_seleccionadas", "solicitudes_ids": [solicitud.pk]})
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "padron/revisar_cambios_sede.html")
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "pendiente")
        with patch("apps.padron.views.enviar_notificacion"):
            respuesta = self.client.post(url, {"accion": "confirmar_aprobacion", "propuesta": respuesta.context["propuesta"]})
        self.assertEqual(respuesta.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "aprobada")
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registros[0]).sede, self.sede)

    def test_propuesta_de_cambio_de_sede_obsoleta_no_se_aplica(self):
        solicitud = SolicitudCambioSede.objects.create(registro_padron=self.registros[0], sede_origen=self.sede_votacion, sede_destino=self.sede)
        self.client.force_login(self.usuario)
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        respuesta = self.client.post(url, {"accion": "aprobar_seleccionadas", "solicitudes_ids": [solicitud.pk]})
        propuesta = respuesta.context["propuesta"]
        self.registros[1].nivel = "4"
        self.registros[1].save(update_fields=("nivel",))
        self.client.post(url, {"accion": "confirmar_aprobacion", "propuesta": propuesta})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "pendiente")
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registros[0]).sede, self.sede_votacion)

    def test_fallo_del_recalculo_revierte_aprobacion_y_sede(self):
        from apps.padron.previsualizacion_cambios import aplicar_cambios_con_recalculo
        solicitud = SolicitudCambioSede.objects.create(registro_padron=self.registros[0], sede_origen=self.sede_votacion, sede_destino=self.sede)
        datos = {"accion": "aprobar_todas", "ids": [solicitud.pk], "maximo": None, "observacion": ""}
        with patch("apps.padron.previsualizacion_cambios.calcular_mesas_automaticas_eleccion", side_effect=ValueError("Conflicto")):
            with self.assertRaisesMessage(ValueError, "Conflicto"):
                aplicar_cambios_con_recalculo(self.eleccion, self.usuario, datos)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "pendiente")
        self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=self.registros[0]).sede, self.sede_votacion)
