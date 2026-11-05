from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.justificativos.models import JustificativoAusencia


@transaction.atomic
def resolver_justificativo(justificativo, *, estado, observacion, usuario):
    from apps.elecciones.models import Eleccion

    eleccion = Eleccion.objects.select_for_update().get(pk=justificativo.registro_padron.eleccion_id)
    actual = JustificativoAusencia.objects.select_for_update().get(pk=justificativo.pk)
    pendiente = actual.estado == JustificativoAusencia.Estado.PENDIENTE
    if (estado == JustificativoAusencia.Estado.APROBADO
            and actual.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD
            and (eleccion.estado != Eleccion.Estado.PUBLICADA or not eleccion.autoridades_confirmadas_en)):
        raise ValidationError("Una ausencia como autoridad solo puede aprobarse tras confirmar las autoridades y mientras la elección está publicada.")
    if estado == JustificativoAusencia.Estado.APROBADO and actual.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD:
        from apps.padron.models import RegistroPadron
        if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
            raise ValidationError("No se pueden modificar autoridades después de emitir el padrón con QR.")
    actual.estado = estado
    actual.observacion_resolucion = observacion
    actual.resuelta_por = usuario
    actual.resuelta_en = timezone.now()
    actual.full_clean()
    actual.save()
    if (estado == JustificativoAusencia.Estado.APROBADO
            and actual.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD
            and actual.reemplazo_procesado_en is None):
        from apps.autoridades.models import AsignacionAutoridad
        from apps.autoridades.services import responder_asignacion

        asignacion = AsignacionAutoridad.objects.select_for_update().filter(
            registro_padron=actual.registro_padron,
        ).first()
        if asignacion is not None:
            if asignacion.estado == AsignacionAutoridad.Estado.ASIGNADA:
                responder_asignacion(asignacion)
                asignacion.refresh_from_db()
                from apps.autoridades.retorno_votacion import intentar_restituir_mesa
                intentar_restituir_mesa(asignacion, usuario)
        actual.reemplazo_procesado_en = timezone.now()
        actual.save(update_fields=("reemplazo_procesado_en",))
    justificativo.refresh_from_db()
    return pendiente
