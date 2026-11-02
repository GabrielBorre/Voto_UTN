"""Reemplazos operativos independientes de la resolución documental."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_administrar_elecciones


def puede_confirmar_reemplazo(usuario, eleccion):
    return eleccion.estado != Eleccion.Estado.FINALIZADA and puede_administrar_elecciones(usuario, eleccion)


@transaction.atomic
def confirmar_reemplazo(asignacion, usuario):
    from apps.autoridades.distribucion import _auditar, es_candidato_electoral

    eleccion = Eleccion.objects.select_for_update().get(pk=asignacion.registro_padron.eleccion_id)
    if not puede_confirmar_reemplazo(usuario, eleccion):
        raise PermissionDenied("No tiene permiso para confirmar reemplazos en esta elección.")
    actual = AsignacionAutoridad.objects.select_for_update().get(pk=asignacion.pk)
    if actual.reemplazo_confirmado_en:
        return actual.reemplazada_por
    if actual.estado != AsignacionAutoridad.Estado.RECHAZADA:
        raise ValidationError("Primero la autoridad debe informar que no asistirá.")
    promovida = None
    suplentes = list(AsignacionAutoridad.objects.select_for_update(of=("self",)).filter(
        mesa=actual.mesa, turno=actual.turno, tipo="suplente", estado="asignada",
    ).select_related("registro_padron__elector", "registro_padron__turno_cursada", "candidatura").order_by("orden_suplencia", "pk"))
    if actual.tipo == "titular":
        for suplente in suplentes:
            registro = suplente.registro_padron
            if (not registro.activo or es_candidato_electoral(registro)
                    or (suplente.candidatura_id and suplente.candidatura.excluida)
                    or (registro.sede_id and not registro.turno_cursada_id)
                    or (registro.turno_cursada_id and registro.turno_cursada.se_superpone_con(actual.turno))
                    or registro.eleccion_claustro_departamento_id != actual.mesa.eleccion_claustro_departamento_id):
                continue
            promovida = suplente
            promovida.tipo = "titular"
            promovida.orden_suplencia = None
            promovida.save(update_fields=("tipo", "orden_suplencia"))
            break
    orden = 0
    for suplente in suplentes:
        if promovida and suplente.pk == promovida.pk:
            continue
        orden += 1
        suplente.orden_suplencia = orden
        suplente.save(update_fields=("orden_suplencia",))
    actual.reemplazo_confirmado_en = timezone.now()
    actual.reemplazo_confirmado_por = usuario
    actual.reemplazada_por = promovida
    actual.save(update_fields=("reemplazo_confirmado_en", "reemplazo_confirmado_por", "reemplazada_por"))
    _auditar(actual.mesa.eleccion_claustro_departamento.eleccion_claustro, usuario,
             "autoridades.reemplazo_confirmado", {"ausente": actual.pk, "promovida": promovida.pk if promovida else None})
    return promovida
