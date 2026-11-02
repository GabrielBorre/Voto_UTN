from django.db import transaction
from django.utils import timezone

from apps.justificativos.models import JustificativoAusencia


@transaction.atomic
def resolver_justificativo(justificativo, *, estado, observacion, usuario):
    from apps.elecciones.models import Eleccion

    eleccion = Eleccion.objects.select_for_update().get(pk=justificativo.registro_padron.eleccion_id)
    actual = JustificativoAusencia.objects.select_for_update().get(pk=justificativo.pk)
    pendiente = actual.estado == JustificativoAusencia.Estado.PENDIENTE
    actual.estado = estado
    actual.observacion_resolucion = observacion
    actual.resuelta_por = usuario
    actual.resuelta_en = timezone.now()
    actual.full_clean()
    actual.save()
    justificativo.refresh_from_db()
    return pendiente
