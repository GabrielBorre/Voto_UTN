"""Cierre definitivo de autoridades de una elección."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion
from apps.padron.models import SolicitudCambioSede
from apps.usuarios.permisos import puede_administrar_elecciones


@transaction.atomic
def confirmar_autoridades(eleccion_id, usuario, fecha_limite):
    from apps.notificaciones.services import crear_notificacion_convocatoria_autoridad, enviar_notificacion

    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion_id)
    if not puede_administrar_elecciones(usuario, eleccion):
        raise PermissionDenied("Solo la Junta puede confirmar autoridades.")
    if eleccion.estado != Eleccion.Estado.PUBLICADA or eleccion.autoridades_confirmadas_en:
        raise ValidationError("Solo se pueden confirmar autoridades una vez, mientras la elección está publicada.")
    if SolicitudCambioSede.objects.filter(registro_padron__eleccion=eleccion, estado=SolicitudCambioSede.Estado.PENDIENTE).exists():
        raise ValidationError("Resolvé todas las solicitudes de cambio de sede pendientes.")
    if eleccion.registros_padron.filter(activo=True, asignacion_mesa__isnull=True).exists():
        raise ValidationError("Todos los electores activos deben tener mesa antes de confirmar autoridades.")
    if not fecha_limite or fecha_limite < timezone.localdate():
        raise ValidationError("Indicá una fecha límite de justificación de hoy o posterior.")
    asignaciones = list(AsignacionAutoridad.objects.filter(
        registro_padron__eleccion=eleccion, estado=AsignacionAutoridad.Estado.ASIGNADA,
    ).select_related("registro_padron__elector", "registro_padron__eleccion", "mesa__sede", "turno"))
    if not asignaciones:
        raise ValidationError("Asigná al menos una autoridad antes de confirmar.")
    eleccion.fecha_limite_justificacion_autoridades = fecha_limite
    eleccion.autoridades_confirmadas_en = timezone.now()
    eleccion.autoridades_confirmadas_por = usuario
    eleccion.save(update_fields=("fecha_limite_justificacion_autoridades", "autoridades_confirmadas_en", "autoridades_confirmadas_por"))
    envios = [crear_notificacion_convocatoria_autoridad(asignacion, fecha_limite) for asignacion in asignaciones]
    transaction.on_commit(lambda: [enviar_notificacion(envio) for envio in envios])
    from apps.auditoria.services import registrar_evento
    registrar_evento(accion="autoridades.confirmadas", entidad="Eleccion", entidad_id=eleccion.pk,
                     eleccion=eleccion, usuario=usuario, datos_nuevos={"cantidad": len(asignaciones), "fecha_limite": fecha_limite.isoformat()})
    return len(asignaciones)
