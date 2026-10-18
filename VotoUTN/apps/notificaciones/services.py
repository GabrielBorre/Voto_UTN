import logging
from smtplib import SMTPException

from django.db import transaction
from django.db.models import Q
from django.core.mail import BadHeaderError, send_mail
from django.utils import timezone

from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.usuarios.models import AsignacionRol, PerfilUsuario
from apps.usuarios.services import elector_de_identidad


logger = logging.getLogger(__name__)


def notificaciones_para_usuario(usuario):
    if not usuario.is_authenticated:
        return EnvioNotificacion.objects.none()
    destinatarios = Q(pk__in=[])
    if not getattr(usuario, "es_elector", False):
        destinatarios |= Q(destinatario=usuario)
    elector = elector_de_identidad(usuario)
    if elector is not None:
        destinatarios |= Q(elector=elector) | Q(destinatario__perfil_electoral__elector=elector)
    return EnvioNotificacion.objects.filter(destinatarios)


def crear_notificacion(*, plantilla, contexto, eleccion=None, destinatario=None, elector=None):
    if destinatario is None and elector is None:
        raise ValueError("La notificación requiere un destinatario o un elector.")
    return EnvioNotificacion.objects.create(
        plantilla=plantilla,
        eleccion=eleccion,
        destinatario=destinatario,
        elector=elector,
        asunto=plantilla.asunto.format(**contexto),
        contenido=plantilla.contenido.format(**contexto),
    )


def crear_notificacion_resultado_justificativo(justificativo):
    elector = justificativo.registro_padron.elector
    eleccion = justificativo.registro_padron.eleccion
    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="justificacion-resolucion",
        defaults={
            "nombre": "Justificación: resolución",
            "categoria": PlantillaNotificacion.Categoria.TRANSACCIONAL,
            "asunto": "Resolución de justificativo: {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "Tu justificativo de {tipo_ausencia} para la elección {nombre_eleccion} "
                "fue {estado_solicitud}.\n\n"
                "Observación: {observacion_resolucion}\n\nVoto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.ELECTOR, AsignacionRol.Rol.AUTORIDAD_MESA],
            "permite_envio_manual": False,
        },
    )
    return crear_notificacion(
        plantilla=plantilla,
        eleccion=eleccion,
        elector=elector,
        contexto={
            "nombre_destinatario": elector.nombre_completo,
            "nombre_eleccion": eleccion.nombre,
            "tipo_ausencia": justificativo.get_ausencia_display().lower(),
            "estado_solicitud": justificativo.get_estado_display().lower(),
            "observacion_resolucion": justificativo.observacion_resolucion or "Sin observaciones.",
        },
    )


def enviar_notificacion(envio):
    correo = envio.elector.correo_electronico if envio.elector_id else envio.destinatario.email
    error = ""
    if not correo:
        error = "El destinatario no tiene correo electrónico."
    else:
        try:
            if send_mail(envio.asunto, envio.contenido, None, [correo], fail_silently=False) != 1:
                error = "El proveedor no confirmó el envío del correo."
        except (SMTPException, OSError, BadHeaderError):
            error = "No se pudo enviar el correo."
    envio.error = error
    envio.estado = EnvioNotificacion.Estado.ERROR if error else EnvioNotificacion.Estado.ENVIADO
    envio.enviada_en = None if error else timezone.now()
    envio.save(update_fields=("estado", "enviada_en", "error"))
    if error:
        logger.warning("Error al enviar la notificacion %s: %s", envio.pk, error)
    return not error


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
    for envio in EnvioNotificacion.objects.filter(estado=EnvioNotificacion.Estado.PENDIENTE).select_related("destinatario", "elector"):
        enviar_notificacion(envio)
        procesados += 1
    return procesados
