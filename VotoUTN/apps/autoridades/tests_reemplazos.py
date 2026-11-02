from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades import tests as base
from apps.autoridades.distribucion import distribuir
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.autoridades.reemplazos import confirmar_reemplazo
from apps.autoridades.services import responder_asignacion
from apps.auditoria.models import EventoAuditoria
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.justificativos.services import resolver_justificativo
from apps.mesas.models import AsignacionMesa, Mesa


class ReemplazosIndependientesTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, suplentes_por_mesa=2)
        for registro in self.registros:
            CandidaturaAutoridad.objects.create(registro_padron=registro, cargada_por=self.usuario)
        distribuir(self.eleccion_claustro, self.usuario)
        self.titular = AsignacionAutoridad.objects.get(tipo="titular")
        self.suplente = AsignacionAutoridad.objects.get(tipo="suplente", orden_suplencia=1)

    def test_aviso_no_promueve_y_confirmacion_sin_documento_es_idempotente(self):
        responder_asignacion(self.titular)
        self.suplente.refresh_from_db()
        self.assertEqual(self.suplente.tipo, "suplente")
        for _ in range(2):
            self.assertEqual(confirmar_reemplazo(self.titular, self.usuario).pk, self.suplente.pk)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular", estado="asignada").count(), 1)
        self.assertEqual(AsignacionAutoridad.objects.get(tipo="suplente").orden_suplencia, 1)
        self.assertEqual(EventoAuditoria.objects.filter(accion="autoridades.reemplazo_confirmado").count(), 1)
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.reemplazo_confirmado_por, self.usuario)

    def test_resolucion_documental_no_promueve_ni_revierte(self):
        justificativo = JustificativoAusencia.objects.create(
            registro_padron=self.titular.registro_padron, ausencia="autoridad",
            tipo=TipoJustificativo.objects.create(nombre="Salud independiente"), detalle="Ausencia",
        )
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.usuario)
        self.suplente.refresh_from_db()
        self.assertEqual(self.suplente.tipo, "suplente")
        responder_asignacion(self.titular)
        confirmar_reemplazo(self.titular, self.usuario)
        resolver_justificativo(justificativo, estado="rechazado", observacion="Revisión", usuario=self.usuario)
        self.suplente.refresh_from_db()
        self.assertEqual(self.suplente.tipo, "titular")

    def test_promocion_con_eleccion_abierta_conserva_mesa_distinta_y_qr(self):
        otra = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                   eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        AsignacionMesa.objects.filter(registro_padron=self.suplente.registro_padron).update(mesa=otra)
        registro = self.suplente.registro_padron
        registro.qr_generado_en = timezone.now()
        registro.numero_mesa_qr = otra.numero
        registro.save()
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado="abierta")
        responder_asignacion(self.titular)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("confirmar-reemplazo-autoridad", args=(self.titular.pk,)), follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.suplente.refresh_from_db()
        self.assertEqual(self.suplente.tipo, "titular")
        confirmar_reemplazo(self.titular, self.usuario)
        registro.refresh_from_db()
        self.assertEqual(registro.asignacion_mesa.mesa_id, otra.pk)
        self.assertEqual(registro.numero_mesa_qr, otra.numero)

    def test_salta_suplente_no_disponible_y_sin_suplentes_deja_vacante(self):
        self.suplente.candidatura.excluida = True
        self.suplente.candidatura.save()
        responder_asignacion(self.titular)
        promovida = confirmar_reemplazo(self.titular, self.usuario)
        self.assertNotEqual(promovida.pk, self.suplente.pk)
        responder_asignacion(promovida)
        self.assertIsNone(confirmar_reemplazo(promovida, self.usuario))
        self.assertFalse(AsignacionAutoridad.objects.filter(tipo="titular", estado="asignada").exists())

    def test_no_permite_confirmar_sin_aviso_ni_redistribuir_con_aviso(self):
        with self.assertRaises(ValidationError):
            confirmar_reemplazo(self.titular, self.usuario)
        responder_asignacion(self.titular)
        with self.assertRaisesMessage(ValidationError, "avisos de ausencia"):
            distribuir(self.eleccion_claustro, self.usuario)

    def test_permisos_cierre_y_endpoint_post(self):
        responder_asignacion(self.titular)
        intruso = get_user_model().objects.create_user(username="sin-permiso-reemplazo")
        with self.assertRaises(PermissionDenied):
            confirmar_reemplazo(self.titular, intruso)
        ruta = reverse("confirmar-reemplazo-autoridad", args=(self.titular.pk,))
        self.client.force_login(intruso)
        self.assertEqual(self.client.post(ruta).status_code, 403)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(ruta).status_code, 404)
        self.assertEqual(self.client.post(ruta).status_code, 302)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.FINALIZADA)
        self.assertEqual(self.client.post(ruta).status_code, 403)
        with self.assertRaises(ValidationError):
            responder_asignacion(self.suplente)

    def test_regeneracion_de_mesas_no_pierde_aviso(self):
        from apps.padron.services import calcular_mesas_automaticas_eleccion
        responder_asignacion(self.titular)
        with self.assertRaisesMessage(ValueError, "avisos de ausencia"):
            calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario, recalcular_sedes=False)
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.estado, "rechazada")

    def test_regeneracion_de_mesas_no_elimina_autoridades_asignadas(self):
        from apps.padron.services import calcular_mesas_automaticas_eleccion
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id"))
        with self.assertRaisesMessage(ValueError, "Hay autoridades asignadas"):
            calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario, recalcular_sedes=False)
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id")), anteriores)

    def test_invalidar_mesas_no_elimina_autoridades_asignadas(self):
        from apps.padron.services import invalidar_mesas_automaticas_alcance
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id"))
        with self.assertRaisesMessage(ValueError, "mesas con autoridades asignadas"):
            invalidar_mesas_automaticas_alcance(self.eleccion_claustro)
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id")), anteriores)

    def test_recalculo_de_sedes_conserva_asignaciones_de_autoridades(self):
        from apps.padron.models import AsignacionSedePadron
        from apps.padron.services import calcular_asignaciones_sede_claustro, invalidar_asignaciones_sede_claustro
        ids = list(AsignacionAutoridad.objects.values_list("registro_padron_id", flat=True))
        anteriores = set(AsignacionSedePadron.objects.filter(registro_padron_id__in=ids).values_list("pk", "registro_padron_id", "sede_id"))
        invalidar_asignaciones_sede_claustro(self.eleccion_claustro)
        calcular_asignaciones_sede_claustro(self.eleccion_claustro)
        posteriores = set(AsignacionSedePadron.objects.filter(registro_padron_id__in=ids).values_list("pk", "registro_padron_id", "sede_id"))
        self.assertEqual(posteriores, anteriores)
