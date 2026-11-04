from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.justificativos.models import JustificativoAusencia


def puede_presentar_justificativo_electoral(registro_padron, momento=None):
    momento = momento or timezone.now()
    eleccion = registro_padron.eleccion
    habilitada_en = eleccion.justificacion_electores_habilitada_en
    if habilitada_en is None or habilitada_en > momento:
        return False
    if (
        eleccion.fecha_limite_justificacion_electores
        and timezone.localdate(momento) > eleccion.fecha_limite_justificacion_electores
    ):
        return False
    return RegistroParticipacion.objects.filter(registro_padron=registro_padron).exists()


def estado_justificativo_electoral(justificativo):
    if justificativo.estado == JustificativoAusencia.Estado.PENDIENTE:
        return "Justificativo Pendiente de Revisión", "warn"
    if justificativo.estado == JustificativoAusencia.Estado.APROBADO:
        return "Inasistencia Justificada", "ok"
    if justificativo.estado == JustificativoAusencia.Estado.RECHAZADO:
        return "Infractor - Justificación Rechazada", "danger"
    raise ValueError(f"Estado de justificativo electoral desconocido: {justificativo.estado}")
