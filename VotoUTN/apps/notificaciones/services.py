from django.db import transaction
from django.core.mail import send_mail
from django.utils import timezone

from apps.notificaciones.models import EnvioNotificacion
from apps.usuarios.models import AsignacionRol, PerfilUsuario


def enviar_resultado_justificativo(justificativo):
    elector = justificativo.registro_padron.elector
    if not elector.correo_electronico:
        return False

    eleccion = justificativo.registro_padron.eleccion
    asunto = f"Resolución de justificativo: {eleccion.nombre}"
    contenido = (
        f"Hola {elector.nombre_completo},\n\n"
        f"Tu justificativo de {justificativo.get_ausencia_display().lower()} "
        f"para la elección {eleccion.nombre} fue {justificativo.get_estado_display().lower()}.\n"
    )
    if justificativo.observacion_resolucion:
        contenido += f"\nObservación: {justificativo.observacion_resolucion}\n"
    contenido += "\nVoto UTN"
    return send_mail(asunto, contenido, None, [elector.correo_electronico], fail_silently=False) == 1


@transaction.atomic
def crear_envios(plantilla, eleccion=None):
    if not plantilla.activa or not plantilla.permite_envio_manual:
        raise ValueError("La plantilla no está habilitada para envíos manuales.")
    usuarios = set()
    roles = plantilla.roles_destinatarios
    asignaciones = AsignacionRol.objects.filter(activo=True, rol__in=roles)
    if eleccion:
        asignaciones = asignaciones.filter(eleccion=eleccion)
    usuarios.update(asignaciones.values_list("usuario_id", flat=True))
    if "elector" in roles and eleccion:
        registros = eleccion.registros_padron.select_related("elector__perfil_usuario", "eleccion_claustro_departamento__eleccion_claustro__claustro")
        if plantilla.claustros.exists():
            registros = registros.filter(eleccion_claustro_departamento__eleccion_claustro__claustro__in=plantilla.claustros.all())
        usuarios.update(PerfilUsuario.objects.filter(elector__registros_padron__in=registros, activo=True).values_list("usuario_id", flat=True))
    envios = [
        EnvioNotificacion(plantilla=plantilla, eleccion=eleccion, destinatario_id=usuario_id, asunto=plantilla.asunto, contenido=plantilla.contenido)
        for usuario_id in usuarios
    ]
    EnvioNotificacion.objects.bulk_create(envios)
    return len(envios)


def procesar_envios_pendientes():
    procesados = 0
    for envio in EnvioNotificacion.objects.filter(estado=EnvioNotificacion.Estado.PENDIENTE).select_related("destinatario"):
        try:
            if envio.destinatario.email:
                send_mail(envio.asunto, envio.contenido, None, [envio.destinatario.email], fail_silently=False)
            envio.estado = EnvioNotificacion.Estado.ENVIADO
            envio.enviada_en = timezone.now()
            envio.error = ""
        except Exception:
            envio.estado = EnvioNotificacion.Estado.ERROR
            envio.error = "No se pudo enviar el correo."
        envio.save(update_fields=("estado", "enviada_en", "error"))
        procesados += 1
    return procesados
