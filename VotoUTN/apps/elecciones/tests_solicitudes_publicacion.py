from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.demo_generadores import generar_solicitudes_demo
from apps.elecciones.forms import FormularioPublicarEleccion
from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionClaustroSede, EleccionSede,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.notificaciones.models import EnvioNotificacion, LoteNotificacion
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron, SolicitudCambioSede
from apps.parametros.models import Claustro, Departamento, Sede, Turno


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SolicitudesPublicacionTests(TestCase):
    def setUp(self):
        hoy = timezone.localdate()
        self.eleccion = Eleccion.objects.create(
            nombre="Escenario de publicación", fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=10),
            fecha_cierre_solicitudes_cambio_sede=hoy + timedelta(days=5),
        )
        self.usuario = get_user_model().objects.create_superuser(username="junta-publicacion")
        self.sedes = {nombre: Sede.objects.create(nombre=nombre) for nombre in ("Campus", "Medrano")}
        ec = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes", abreviatura="EST"),
        )
        self.alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=ec,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="K"),
        )
        for sede in self.sedes.values():
            EleccionSede.objects.create(eleccion=self.eleccion, sede=sede)
            EleccionClaustroSede.objects.create(eleccion_claustro=ec, sede=sede)
            EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.alcance, sede=sede)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion, eleccion_claustro_departamento=self.alcance,
            sede=self.sedes["Campus"], numero=1,
        )
        turno = Turno.objects.create(nombre="Mañana", hora_inicio="08:00", hora_fin="12:00")
        self.registros = []
        for indice in range(2, 42):
            registro = self.crear_registro(str(36000000 + indice))
            self.registros.append(registro)
            if indice in (12, 15, 16):
                AsignacionAutoridad.objects.create(
                    registro_padron=registro, mesa=self.mesa, turno=turno, asignada_por=self.usuario,
                )
        self.carlos = self.crear_registro("38999222")

    def crear_registro(self, dni, alcance=None):
        registro = RegistroPadron.objects.create(
            elector=Elector.objects.create(dni=dni, legajo=dni, tipo_documento="DNI", nombre="Demo"),
            eleccion=self.eleccion, eleccion_claustro_departamento=alcance or self.alcance,
        )
        AsignacionSedePadron.objects.create(registro_padron=registro, sede=self.sedes["Campus"], estado="asignada")
        AsignacionMesa.objects.create(registro_padron=registro, mesa=self.mesa)
        return registro

    def test_publicacion_crea_30_estudiantes_sin_autoridades_y_conserva_mesas(self):
        autoridades = list(AsignacionAutoridad.objects.order_by("pk").values())
        mesas = list(AsignacionMesa.objects.order_by("pk").values())
        self.eleccion.cambiar_estado("publicada")
        solicitudes = SolicitudCambioSede.objects.all()
        self.assertEqual(solicitudes.count(), 30)
        self.assertFalse(solicitudes.filter(registro_padron__elector_id__in=(
            AsignacionAutoridad.objects.values("registro_padron__elector_id")
        )).exists())
        self.assertEqual(set(solicitudes.values_list(
            "registro_padron__eleccion_claustro_departamento__eleccion_claustro__claustro__abreviatura",
            flat=True,
        )), {"EST"})
        self.assertFalse(solicitudes.filter(registro_padron=self.carlos).exists())
        self.assertEqual(list(AsignacionAutoridad.objects.order_by("pk").values()), autoridades)
        self.assertEqual(list(AsignacionMesa.objects.order_by("pk").values()), mesas)

    def test_publicacion_web_no_envia_correo_y_encola_un_solo_lote(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(fecha_cierre_solicitudes_cambio_sede=None)
        self.client.force_login(self.usuario)
        limite = timezone.localdate()
        with patch("apps.notificaciones.services.send_mail") as correo:
            respuesta = self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {
                "estado": "publicada", "fecha_cierre_solicitudes_cambio_sede": limite.isoformat(),
            })
        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, limite)
        self.assertEqual(SolicitudCambioSede.objects.count(), 30)
        self.assertEqual(LoteNotificacion.objects.count(), 1)
        self.assertFalse(EnvioNotificacion.objects.exists())
        correo.assert_not_called()

    def test_publicacion_utiliza_el_nuevo_plazo_en_lugar_del_anterior_vencido(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(
            fecha_cierre_solicitudes_cambio_sede=timezone.localdate() - timedelta(days=1),
        )
        self.eleccion.refresh_from_db()
        limite = timezone.localdate() + timedelta(days=2)
        formulario = FormularioPublicarEleccion(
            {"fecha_cierre_solicitudes_cambio_sede": limite.isoformat()},
            eleccion=self.eleccion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.publicar()
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, limite)
        self.assertEqual(SolicitudCambioSede.objects.count(), 30)

    def test_error_publicando_revierte_tambien_el_plazo_del_formulario(self):
        limite_original = self.eleccion.fecha_cierre_solicitudes_cambio_sede
        formulario = FormularioPublicarEleccion(
            {"fecha_cierre_solicitudes_cambio_sede": timezone.localdate().isoformat()},
            eleccion=self.eleccion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        with patch(
            "apps.elecciones.demo_generadores.generar_solicitudes_demo",
            side_effect=IntegrityError("Fallo de prueba"),
        ), self.assertRaises(IntegrityError):
            formulario.publicar()
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_PREPARACION)
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, limite_original)
        self.assertIsNone(self.eleccion.solicitudes_cambio_sede_habilitadas_en)
        self.assertFalse(SolicitudCambioSede.objects.exists())
        self.assertFalse(LoteNotificacion.objects.exists())

    def test_menos_de_30_crea_solo_las_posibles(self):
        RegistroPadron.objects.exclude(pk__in=[r.pk for r in self.registros[:2]]).update(activo=False)
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(SolicitudCambioSede.objects.count(), 2)

    def test_no_utiliza_otros_claustros_para_completar_el_lote(self):
        RegistroPadron.objects.all().update(activo=False)
        docentes = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Docentes", abreviatura="DOC"),
        )
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=docentes, departamento=self.alcance.departamento,
        )
        for sede in self.sedes.values():
            EleccionClaustroSede.objects.create(eleccion_claustro=docentes, sede=sede)
            EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=sede)
        self.crear_registro("45000000", alcance)
        self.registros[0].activo = True
        self.registros[0].save(update_fields=["activo"])
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(SolicitudCambioSede.objects.count(), 1)

    def test_omite_actividad_qr_y_destinos_incompatibles(self):
        RegistroPadron.objects.filter(pk=self.registros[0].pk).update(qr_generado_en=timezone.now())
        RegistroPadron.objects.filter(pk=self.registros[1].pk).update(sede=self.sedes["Campus"])
        AsignacionSedePadron.objects.filter(registro_padron=self.registros[2]).delete()
        self.eleccion.cambiar_estado("publicada")
        self.assertEqual(SolicitudCambioSede.objects.count(), 30)
        self.assertFalse(SolicitudCambioSede.objects.filter(registro_padron__in=self.registros[:3]).exists())

    def test_sin_sede_alternativa_no_inventa_solicitudes(self):
        self.sedes["Medrano"].activa = False
        self.sedes["Medrano"].save(update_fields=["activa"])
        self.eleccion.cambiar_estado("publicada")
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_comando_repetido_conserva_resoluciones_y_no_supera_30(self):
        self.eleccion.cambiar_estado("publicada")
        solicitud = SolicitudCambioSede.objects.first()
        solicitud.estado = "aprobada"
        solicitud.save(update_fields=["estado"])
        anteriores = list(SolicitudCambioSede.objects.order_by("pk").values())
        call_command("generar_solicitudes_cambio_sede_demo", stdout=StringIO())
        self.assertEqual(list(SolicitudCambioSede.objects.order_by("pk").values()), anteriores)
        self.assertEqual(generar_solicitudes_demo(self.eleccion), 0)

    def test_error_persistiendo_revierte_publicacion_y_lote(self):
        guardar = SolicitudCambioSede.save
        contador = 0

        def fallar(solicitud, *args, **kwargs):
            nonlocal contador
            contador += 1
            if contador == 5:
                raise IntegrityError("Fallo de prueba")
            return guardar(solicitud, *args, **kwargs)

        with patch.object(SolicitudCambioSede, "save", fallar), self.assertRaises(IntegrityError):
            self.eleccion.cambiar_estado("publicada")
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, "en_preparacion")
        self.assertFalse(SolicitudCambioSede.objects.exists())
