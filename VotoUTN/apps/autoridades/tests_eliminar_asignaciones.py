from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.autoridades.distribucion import distribuir, eliminar_asignaciones
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades
from apps.autoridades import tests as casos_base
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.mesas.models import AsignacionMesa, Mesa
from apps.parametros.models import Claustro
from apps.usuarios.models import AsignacionRol


class EliminarAsignacionesTests(TestCase):
    def setUp(self):
        casos_base.TurnosAutoridadesTests.setUp(self)
        self.opciones = ConfiguracionAutoridades.objects.create(
            eleccion_claustro=self.eleccion_claustro, modo="aleatorio",
        )
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=2, suplentes_por_mesa=0)
        for registro in self.registros:
            CandidaturaAutoridad.objects.create(registro_padron=registro, cargada_por=self.usuario)
        distribuir(self.eleccion_claustro, self.usuario)
        self.asignaciones = list(AsignacionAutoridad.objects.select_related("candidatura"))
        self.rol_autoridad = AsignacionRol.objects.create(
            usuario=self.usuario, rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=self.eleccion, sede=self.sede_votacion, mesa=self.mesa,
        )
        self.ruta = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        self.client.force_login(self.usuario)

    def test_eliminar_confirmado_vacia_autoridades_y_limpia_selecciones(self):
        candidatura = self.asignaciones[0].candidatura
        candidatura.mesa_manual = self.mesa
        candidatura.turno_manual = self.manana
        candidatura.tipo_manual = self.asignaciones[0].tipo
        candidatura.orden_manual = self.asignaciones[0].orden_suplencia
        candidatura.mesa_traslado = self.mesa
        candidatura.turno_traslado = self.manana
        candidatura.save()
        CandidaturaAutoridad.objects.exclude(pk__in=[a.candidatura_id for a in self.asignaciones]).update(excluida=True)
        AsignacionMesa.objects.update(autoridad_al_final=True)
        padron = list(AsignacionMesa.objects.order_by("pk").values_list("pk", "registro_padron_id", "mesa_id"))
        self.opciones.modo = "manual"
        self.opciones.save()

        respuesta = self.client.post(self.ruta, {"eliminar-asignaciones": "1", "confirmar-eliminacion": "1"}, follow=True)

        self.assertContains(respuesta, "Se eliminaron 2 asignaciones")
        self.assertFalse(AsignacionAutoridad.objects.exists())
        self.assertFalse(AsignacionRol.objects.filter(pk=self.rol_autoridad.pk).exists())
        self.assertTrue(AsignacionRol.objects.filter(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA).exists())
        self.assertFalse(CandidaturaAutoridad.objects.exclude(mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None, mesa_traslado=None, turno_traslado=None).exists())
        self.assertEqual(CandidaturaAutoridad.objects.count(), 3)
        self.assertEqual(CandidaturaAutoridad.objects.filter(excluida=True).count(), 1)
        self.assertEqual(list(AsignacionMesa.objects.order_by("pk").values_list("pk", "registro_padron_id", "mesa_id")), padron)
        self.assertFalse(AsignacionMesa.objects.filter(autoridad_al_final=True).exists())
        self.assertEqual(self.eleccion_claustro.turnos_autoridad.get().titulares_por_mesa, 2)
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "manual")
        evento = EventoAuditoria.objects.get(accion="autoridades.asignaciones_eliminadas")
        self.assertEqual(evento.usuario_id, self.usuario.pk)
        self.assertEqual(evento.datos_nuevos["eliminadas"], 2)
        self.assertEqual({a["id"] for a in evento.datos_nuevos["asignaciones_anteriores"]}, {a.pk for a in self.asignaciones})

    def test_get_y_post_sin_confirmacion_no_eliminan(self):
        respuesta = self.client.get(self.ruta, {"eliminar-asignaciones": "1", "confirmar-eliminacion": "1"})
        self.assertContains(respuesta, "Eliminar todas las asignaciones")
        for confirmacion in (None, "", "0"):
            with self.subTest(confirmacion=confirmacion):
                datos = {"eliminar-asignaciones": "1"}
                if confirmacion is not None:
                    datos["confirmar-eliminacion"] = confirmacion
                respuesta = self.client.post(self.ruta, datos, follow=True)
                self.assertContains(respuesta, "Confirmá la eliminación")
                self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        self.assertFalse(EventoAuditoria.objects.filter(accion="autoridades.asignaciones_eliminadas").exists())

    def test_eliminar_no_afecta_asignaciones_roles_ni_selecciones_de_otro_claustro(self):
        otro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Otro claustro"))
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro, departamento=self.mesa.eleccion_claustro_departamento.departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=self.sede_votacion)
        mesa = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion, eleccion_claustro_departamento=alcance)
        registro = next(r for r in self.registros if r.pk not in {a.registro_padron_id for a in self.asignaciones})
        registro.eleccion_claustro_departamento = alcance
        registro.save()
        AsignacionMesa.objects.filter(registro_padron=registro).update(mesa=mesa, autoridad_al_final=True)
        candidatura = CandidaturaAutoridad.objects.get(registro_padron=registro)
        candidatura.mesa_manual = mesa
        candidatura.turno_manual = self.manana
        candidatura.tipo_manual = "titular"
        candidatura.save()
        asignacion = AsignacionAutoridad.objects.create(
            registro_padron=registro, candidatura=candidatura, mesa=mesa, turno=self.manana, asignada_por=self.usuario,
        )
        rol = AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.AUTORIDAD_MESA, eleccion=self.eleccion, sede=self.sede_votacion, mesa=mesa)

        self.assertEqual(eliminar_asignaciones(self.eleccion_claustro, self.usuario), 2)

        self.assertEqual(list(AsignacionAutoridad.objects.values_list("pk", flat=True)), [asignacion.pk])
        self.assertTrue(AsignacionRol.objects.filter(pk=rol.pk).exists())
        candidatura.refresh_from_db()
        self.assertEqual(candidatura.mesa_manual_id, mesa.pk)
        self.assertTrue(AsignacionMesa.objects.get(registro_padron=registro).autoridad_al_final)

    def test_eliminar_respeta_eleccion_abierta_o_cerrada(self):
        for estado in (Eleccion.Estado.EN_CURSO, Eleccion.Estado.FINALIZADA):
            with self.subTest(estado=estado):
                Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=estado)
                respuesta = self.client.post(self.ruta, {"eliminar-asignaciones": "1", "confirmar-eliminacion": "1"}, follow=True)
                self.assertEqual(respuesta.status_code, 403)
                self.assertEqual(AsignacionAutoridad.objects.count(), 2)

    def test_eliminar_respeta_qr_y_avisos_de_ausencia(self):
        registro = self.registros[0]
        registro.qr_generado_en = timezone.now()
        registro.save()
        with self.assertRaisesMessage(ValidationError, "imprimible"):
            eliminar_asignaciones(self.eleccion_claustro, self.usuario)
        registro.qr_generado_en = None
        registro.save()
        AsignacionAutoridad.objects.filter(pk=self.asignaciones[0].pk).update(respondida_en=timezone.now())
        with self.assertRaisesMessage(ValidationError, "avisos de ausencia"):
            eliminar_asignaciones(self.eleccion_claustro, self.usuario)
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        self.assertTrue(AsignacionRol.objects.filter(pk=self.rol_autoridad.pk).exists())

    def test_sin_permiso_o_sin_csrf_no_se_puede_eliminar(self):
        usuario = get_user_model().objects.create_user(username="sin-permiso-eliminar")
        self.client.force_login(usuario)
        respuesta = self.client.post(self.ruta, {"eliminar-asignaciones": "1", "confirmar-eliminacion": "1"})
        self.assertEqual(respuesta.status_code, 403)
        with self.assertRaises(PermissionDenied):
            eliminar_asignaciones(self.eleccion_claustro, usuario)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(self.ruta, {"eliminar-asignaciones": "1", "confirmar-eliminacion": "1"}).status_code, 403)
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)

    def test_fallo_revierte_eliminacion_roles_y_selecciones(self):
        candidatura = self.asignaciones[0].candidatura
        candidatura.mesa_manual = self.mesa
        candidatura.save()
        with patch("apps.autoridades.distribucion._auditar", side_effect=RuntimeError("Fallo al auditar")):
            with self.assertRaisesMessage(RuntimeError, "Fallo al auditar"):
                eliminar_asignaciones(self.eleccion_claustro, self.usuario)
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        self.assertTrue(AsignacionRol.objects.filter(pk=self.rol_autoridad.pk).exists())
        candidatura.refresh_from_db()
        self.assertEqual(candidatura.mesa_manual_id, self.mesa.pk)

    def test_eliminar_es_idempotente_y_permite_un_sorteo_posterior(self):
        self.assertEqual(eliminar_asignaciones(self.eleccion_claustro, self.usuario), 2)
        self.assertEqual(eliminar_asignaciones(self.eleccion_claustro, self.usuario), 0)
        self.assertFalse(AsignacionAutoridad.objects.exists())
        resultado = distribuir(self.eleccion_claustro, self.usuario)
        self.assertEqual(resultado["asignadas"], 2)
        self.assertEqual(resultado["conservadas"], 0)
