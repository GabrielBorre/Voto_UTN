from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades import tests as base
from apps.autoridades.models import AsignacionAutoridad
from apps.autoridades.services import asignar_autoridad
from apps.autoridades.traslados_vacantes import candidatos_para_vacante, confirmar_traslado_por_vacante
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.justificativos.services import resolver_justificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.notificaciones.models import EnvioNotificacion


class TrasladosPorVacanteTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        self.mesa_origen = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
        )
        self.ausente, _ = asignar_autoridad(self.registros[0], self.mesa, self.manana, self.usuario)
        self.candidata, _ = asignar_autoridad(self.registros[1], self.mesa_origen, self.manana, self.usuario)
        self.otra, _ = asignar_autoridad(self.registros[2], self.mesa_origen, self.manana, self.usuario)
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.PUBLICADA, autoridades_confirmadas_en=timezone.now())
        justificativo = JustificativoAusencia.objects.create(
            registro_padron=self.ausente.registro_padron, ausencia="autoridad",
            tipo=TipoJustificativo.objects.create(nombre="Ausencia"), detalle="No puede ejercer",
        )
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.usuario)
        self.ausente.refresh_from_db()

    def test_propuesta_y_confirmacion_conservan_votacion_y_notifican(self):
        self.assertEqual(set(candidatos_para_vacante(self.ausente).values_list("pk", flat=True)), {self.candidata.pk, self.otra.pk})
        mesa_votacion = AsignacionMesa.objects.get(registro_padron=self.candidata.registro_padron).mesa_id
        self.client.force_login(self.usuario)
        pagina = self.client.get(reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk)))
        self.assertContains(pagina, "Propuesta para cubrir la vacante")
        with patch("apps.notificaciones.services.enviar_notificacion") as enviar:
            with self.captureOnCommitCallbacks(execute=True):
                confirmar_traslado_por_vacante(self.ausente, self.candidata.pk, self.usuario)
            enviar.assert_called_once()
        self.candidata.refresh_from_db()
        self.assertEqual(self.candidata.mesa_id, self.mesa.pk)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.candidata.registro_padron).mesa_id, mesa_votacion)
        self.assertEqual(AsignacionAutoridad.objects.filter(mesa=self.mesa_origen, turno=self.manana, estado="asignada").count(), 1)
        avisos = EnvioNotificacion.objects.filter(plantilla__codigo="autoridad-cambio-mesa-vacante")
        self.assertEqual(avisos.count(), 1)
        self.assertNotIn(self.mesa.codigo, avisos.get().contenido)
        self.ausente.refresh_from_db()
        self.assertEqual(self.ausente.reemplazada_por_id, self.candidata.pk)
        with self.assertRaises(ValidationError):
            confirmar_traslado_por_vacante(self.ausente, self.otra.pk, self.usuario)

    def test_no_propone_si_mesa_origen_quedaria_sin_titular(self):
        self.otra.estado = "rechazada"
        self.otra.save(update_fields=("estado",))
        self.assertFalse(candidatos_para_vacante(self.ausente).exists())
        with self.assertRaises(ValidationError):
            confirmar_traslado_por_vacante(self.ausente, self.candidata.pk, self.usuario)
        self.candidata.refresh_from_db()
        self.assertEqual(self.candidata.mesa_id, self.mesa_origen.pk)

    def test_no_se_traslada_en_curso(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_CURSO)
        with self.assertRaises(PermissionDenied):
            confirmar_traslado_por_vacante(self.ausente, self.candidata.pk, self.usuario)
        self.candidata.refresh_from_db()
        self.assertEqual(self.candidata.mesa_id, self.mesa_origen.pk)

    def test_respeta_minimo_configurado_de_dos_titulares(self):
        from apps.elecciones.models import EleccionClaustroTurno
        from apps.padron.models import Elector, RegistroPadron

        config = EleccionClaustroTurno.objects.get(eleccion_claustro=self.eleccion_claustro, turno=self.manana)
        config.titulares_por_mesa = 3
        config.minimo_titulares_por_mesa = 2
        config.save()
        self.assertFalse(candidatos_para_vacante(self.ausente).exists())
        elector = Elector.objects.create(dni="40999999", nombre="Tercera autoridad")
        registro = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
            sede=self.sede, turno_cursada=self.tarde,
        )
        asignar_autoridad(registro, self.mesa_origen, self.manana, self.usuario)
        self.assertEqual(candidatos_para_vacante(self.ausente).count(), 3)
        with patch("apps.notificaciones.services.enviar_notificacion"):
            confirmar_traslado_por_vacante(self.ausente, self.candidata.pk, self.usuario)
        self.assertEqual(AsignacionAutoridad.objects.filter(mesa=self.mesa_origen, turno=self.manana, estado="asignada").count(), 2)
