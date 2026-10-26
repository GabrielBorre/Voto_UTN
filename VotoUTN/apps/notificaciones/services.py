import logging
from smtplib import SMTPException

from django.db import transaction
from django.db.models import Q
from django.core.mail import BadHeaderError, send_mail
from django.utils import timezone

from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.elecciones.models import Eleccion
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
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


def crear_notificacion_resultado_cambio_sede(solicitud):
    elector = solicitud.registro_padron.elector
    eleccion = solicitud.registro_padron.eleccion
    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="cambio-sede-resolucion",
        defaults={
            "nombre": "Cambio de sede: resolución",
            "categoria": PlantillaNotificacion.Categoria.TRANSACCIONAL,
            "asunto": "Resolución de solicitud de cambio de sede: {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "Tu solicitud de cambio de sede para la elección {nombre_eleccion} "
                "fue {estado_solicitud}.\n\n"
                "Sede solicitada: {sede_solicitada}\n"
                "Observación: {observacion_resolucion}\n\nVoto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.ELECTOR],
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
            "estado_solicitud": solicitud.get_estado_display().lower(),
            "sede_solicitada": solicitud.sede_destino.nombre,
            "observacion_resolucion": solicitud.observacion_resolucion or "Sin observaciones.",
        },
    )


def notificar_eleccion_publicada(eleccion):
    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="eleccion-publicada-padron-definitivo",
        defaults={
            "nombre": "Elección publicada: padrón definitivo",
            "categoria": PlantillaNotificacion.Categoria.JORNADA,
            "asunto": "Padrón definitivo disponible: {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "La elección {nombre_eleccion} fue publicada y el padrón definitivo ya está disponible.\n"
                "Podés revisar tu sede de votación y solicitar cambio de sede hasta la fecha de cierre habilitada.\n\n"
                "Voto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.ELECTOR],
            "permite_envio_manual": False,
        },
    )
    _notificar_electores_de_eleccion(eleccion, plantilla)


def notificar_eleccion_en_curso(eleccion):
    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="eleccion-en-curso-asignacion-mesa",
        defaults={
            "nombre": "Elección en curso: sede y mesa",
            "categoria": PlantillaNotificacion.Categoria.JORNADA,
            "asunto": "Tu mesa para {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "La elección {nombre_eleccion} está en curso.\n"
                "Tu sede asignada es {sede} y tu mesa es {mesa}.\n\n"
                "Voto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.ELECTOR],
            "permite_envio_manual": False,
        },
    )
    _notificar_electores_de_eleccion(eleccion, plantilla)


@transaction.atomic
def crear_notificaciones_ausentes_confirmadas(eleccion):
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado != Eleccion.Estado.ABIERTA:
        raise ValueError("Las notificaciones de ausentes solo se pueden confirmar durante una elección en curso.")
    if eleccion.notificaciones_ausentes_confirmadas_en:
        raise ValueError("Las notificaciones a ausentes ya fueron confirmadas para esta elección.")
    mesas = Mesa.objects.filter(eleccion=eleccion)
    if not mesas.exists():
        raise ValueError("La elección no tiene mesas para verificar el cierre del escaneo.")
    if mesas.exclude(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA).exists():
        raise ValueError("Todas las mesas deben estar escaneadas y confirmadas antes de notificar a los ausentes.")

    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="aviso-ausentes-eleccion",
        defaults={
            "nombre": "Ausentes: período de justificativos",
            "categoria": PlantillaNotificacion.Categoria.JORNADA,
            "asunto": "Información sobre tu participación: {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "En los registros de la elección {nombre_eleccion} figurás como ausente. "
                "Podés presentar un justificativo dentro del período habilitado desde Voto UTN.\n\n"
                "Si considerás que esta información es incorrecta, comunicate con la Junta Electoral.\n\n"
                "Voto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.ELECTOR],
            "permite_envio_manual": False,
        },
    )
    registros_ausentes = RegistroPadron.objects.filter(
        eleccion=eleccion,
        activo=True,
        asignacion_mesa__mesa__estado_escaneo=Mesa.EstadoEscaneo.PROCESADA,
        participaciones__isnull=False,
    ).select_related("elector").distinct()
    envios = [
        EnvioNotificacion(
            plantilla=plantilla,
            eleccion=eleccion,
            elector=registro.elector,
            asunto=plantilla.asunto.format(
                nombre_destinatario=registro.elector.nombre_completo,
                nombre_eleccion=eleccion.nombre,
            ),
            contenido=plantilla.contenido.format(
                nombre_destinatario=registro.elector.nombre_completo,
                nombre_eleccion=eleccion.nombre,
            ),
        )
        for registro in registros_ausentes
    ]
    EnvioNotificacion.objects.bulk_create(envios)
    eleccion.notificaciones_ausentes_confirmadas_en = timezone.now()
    eleccion.save(update_fields=("notificaciones_ausentes_confirmadas_en",))
    return envios


def _notificar_electores_de_eleccion(eleccion, plantilla):
    from apps.padron.models import RegistroPadron

    registros = RegistroPadron.objects.filter(eleccion=eleccion, activo=True).select_related(
        "elector",
        "sede",
        "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento",
    )
    for registro in registros:
        envio = crear_notificacion(
            plantilla=plantilla,
            eleccion=eleccion,
            elector=registro.elector,
            contexto={
                "nombre_destinatario": registro.elector.nombre_completo,
                "nombre_eleccion": eleccion.nombre,
                "sede": registro.sede.nombre if registro.sede_id else "Sin asignar",
                "mesa": registro.asignacion_mesa.mesa.codigo if hasattr(registro, "asignacion_mesa") else "Sin asignar",
            },
        )
        enviar_notificacion(envio)


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
