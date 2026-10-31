from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.elecciones.models import Eleccion
from apps.elecciones.calendario_forms import formulario_calendario, guardar_calendario
from apps.parametros.models import FechaAdministrativa
from apps.notificaciones.models import MensajeProgramado, PlantillaNotificacion, EnvioNotificacion
from apps.notificaciones.calendario import procesar_calendario
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.usuarios.models import AsignacionRol


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CalendarioTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(nombre="Calendario", fecha_inicio=timezone.localdate(), fecha_fin=timezone.localdate()+timedelta(days=30), estado="publicada")
        self.plantilla = PlantillaNotificacion.objects.create(codigo="prueba-calendario", nombre="Calendario", asunto="{nombre_eleccion}", contenido="Hola {nombre_destinatario}", roles_destinatarios=["administrador_junta"])
        self.fecha = FechaAdministrativa.objects.create(codigo="fecha-prueba", nombre="Fecha prueba", roles_destinatarios=["administrador_junta"], envia_mensaje=True, permite_recordatorios=True, plantilla_mensaje=self.plantilla)
        usuario = get_user_model().objects.create_user(username="junta-calendario", email="junta@example.com")
        AsignacionRol.objects.create(usuario=usuario, rol="administrador_junta", eleccion=self.eleccion)

    def mensaje(self, dias=2, **kwargs):
        return MensajeProgramado.objects.create(eleccion=self.eleccion, fecha_administrativa=self.fecha, estado_eleccion="publicada", plantilla=self.plantilla, programado_para=timezone.now()+timedelta(days=dias), **kwargs)

    def test_pendiente_futuro_bloquea_avance(self):
        self.mensaje()
        with self.assertRaisesMessage(ValidationError, "mensajes futuros pendientes"):
            self.eleccion.cambiar_estado("en_curso")
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, "publicada")

    def test_worker_no_envia_antes_y_no_duplica(self):
        mensaje = self.mensaje()
        self.assertEqual(procesar_calendario(), 0)
        MensajeProgramado.objects.filter(pk=mensaje.pk).update(programado_para=timezone.now()-timedelta(minutes=1))
        self.assertEqual(procesar_calendario(), 1)
        self.assertEqual(procesar_calendario(), 0)
        self.assertEqual(EnvioNotificacion.objects.count(), 1)
        self.assertEqual(EnvioNotificacion.objects.get().estado, "enviado")

    def test_deshabilitado_no_envia(self):
        self.mensaje(-1, habilitado=False)
        self.assertEqual(procesar_calendario(), 0)
        self.assertFalse(EnvioNotificacion.objects.exists())

    def test_vencido_de_estado_anterior_se_procesa(self):
        self.mensaje(-1)
        self.eleccion.estado = "en_curso"
        self.eleccion.save(update_fields=("estado",))
        self.assertEqual(procesar_calendario(), 1)

    def test_plantilla_con_plazo_no_inventa_fecha_de_tramite(self):
        mensaje = self.mensaje(-1)
        self.plantilla.contenido = "Cierra el {fecha_fin}"
        self.plantilla.save()
        self.assertEqual(procesar_calendario(), 0)
        mensaje.refresh_from_db()
        self.assertIn("fecha_fin", mensaje.error)
        self.assertFalse(EnvioNotificacion.objects.exists())

    def test_no_permite_editar_historial_procesado(self):
        mensaje = self.mensaje(-1, procesado_en=timezone.now())
        datos = self.datos((timezone.localdate()+timedelta(days=2)).isoformat()+"T12:00")
        datos.update({"mensajes-INITIAL_FORMS": "1", "mensajes-0-id": mensaje.pk})
        self.assertFalse(formulario_calendario(self.eleccion, "publicada", datos).is_valid())

    def test_rehabilitar_vencido_exige_fecha_futura(self):
        mensaje = self.mensaje(-1, habilitado=False)
        datos = self.datos(timezone.localtime(mensaje.programado_para).strftime("%Y-%m-%dT%H:%M"))
        datos.update({"mensajes-INITIAL_FORMS": "1", "mensajes-0-id": mensaje.pk})
        self.assertFalse(formulario_calendario(self.eleccion, "publicada", datos).is_valid())

    def test_formulario_invalido_no_lanza_excepcion(self):
        datos = self.datos("fecha-invalida")
        datos["mensajes-0-fecha_administrativa"] = "9999999"
        self.assertFalse(formulario_calendario(self.eleccion, "publicada", datos).is_valid())

    def test_deshabilitar_conserva_registro(self):
        mensaje = self.mensaje()
        datos = self.datos(timezone.localtime(mensaje.programado_para).strftime("%Y-%m-%dT%H:%M"))
        datos.update({"mensajes-INITIAL_FORMS": "1", "mensajes-0-id": mensaje.pk, "mensajes-0-DELETE": "on"})
        formulario = formulario_calendario(self.eleccion, "publicada", datos)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        guardar_calendario(formulario, self.eleccion, "publicada")
        mensaje.refresh_from_db()
        self.assertFalse(mensaje.habilitado)

    def test_transicion_guarda_calendario_y_no_envia_avisos_directos(self):
        self.client.force_login(get_user_model().objects.get(username="junta-calendario"))
        self.eleccion.estado = "en_preparacion"
        self.eleccion.save(update_fields=("estado",))
        datos = self.datos((timezone.localdate()+timedelta(days=2)).isoformat()+"T12:00")
        datos["estado"] = "publicada"
        with patch.object(Eleccion, "validar_configuracion"):
            respuesta = self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), datos)
        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, "publicada")
        self.assertEqual(self.eleccion.mensajes_programados.count(), 1)
        self.assertFalse(EnvioNotificacion.objects.exists())

    def test_transicion_con_fecha_invalida_no_cambia_estado(self):
        self.client.force_login(get_user_model().objects.get(username="junta-calendario"))
        self.eleccion.estado = "en_preparacion"
        self.eleccion.save(update_fields=("estado",))
        datos = self.datos(timezone.localdate().isoformat()+"T12:00")
        datos["estado"] = "publicada"
        respuesta = self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), datos)
        self.assertEqual(respuesta.status_code, 400)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, "en_preparacion")
        self.assertFalse(MensajeProgramado.objects.exists())

    def test_otro_estado_no_envia(self):
        mensaje = self.mensaje(-1)
        mensaje.estado_eleccion = "en_curso"
        mensaje.save()
        self.assertEqual(procesar_calendario(), 0)

    def datos(self, dia):
        return {"mensajes-TOTAL_FORMS":"1", "mensajes-INITIAL_FORMS":"0", "mensajes-0-fecha_administrativa":self.fecha.pk, "mensajes-0-plantilla":self.plantilla.pk, "mensajes-0-programado_para":dia, "mensajes-0-habilitado":"on"}

    def test_fecha_minima_manana_y_guardado(self):
        datos=self.datos(timezone.localdate().isoformat()+"T12:00")
        self.assertFalse(formulario_calendario(self.eleccion, "publicada", datos).is_valid())
        datos["mensajes-0-programado_para"]=(timezone.localdate()+timedelta(days=1)).isoformat()+"T12:00"
        formulario=formulario_calendario(self.eleccion, "publicada", datos)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        guardar_calendario(formulario, self.eleccion, "publicada")
        self.assertEqual(MensajeProgramado.objects.count(),1)

    def test_plantilla_fuera_del_alcance_rechazada(self):
        self.plantilla.roles_destinatarios=["elector"]
        self.plantilla.save()
        datos=self.datos((timezone.localdate()+timedelta(days=2)).isoformat()+"T12:00")
        self.assertFalse(formulario_calendario(self.eleccion,"publicada",datos).is_valid())

    def test_error_creando_envios_no_deja_envios_parciales(self):
        mensaje=self.mensaje(-1)
        with patch("apps.notificaciones.calendario.crear_notificacion", side_effect=ValueError("Fallo")):
            self.assertEqual(procesar_calendario(),0)
        mensaje.refresh_from_db()
        self.assertIsNone(mensaje.procesado_en)
        self.assertEqual(mensaje.error,"Fallo")
        self.assertFalse(EnvioNotificacion.objects.exists())
