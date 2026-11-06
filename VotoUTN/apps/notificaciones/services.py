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


def crear_notificacion_convocatoria_autoridad(asignacion, fecha_limite):
    elector = asignacion.registro_padron.elector
    eleccion = asignacion.registro_padron.eleccion
    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="autoridad-convocatoria-definitiva",
        defaults={"nombre": "Convocatoria como autoridad", "categoria": PlantillaNotificacion.Categoria.TRANSACCIONAL,
                  "asunto": "Convocatoria como autoridad: {nombre_eleccion}",
                  "contenido": "Hola {nombre},\n\nFuiste convocado como autoridad para {nombre_eleccion} en {sede}, turno {turno}. Podés justificar tu imposibilidad hasta el {fecha}. La mesa definitiva se informará al comenzar la elección.\n\nVoto UTN",
                  "roles_destinatarios": [AsignacionRol.Rol.AUTORIDAD_MESA], "permite_envio_manual": False},
    )
    return crear_notificacion(plantilla=plantilla, eleccion=eleccion, elector=elector,
                              contexto={"nombre": elector.nombre_completo, "nombre_eleccion": eleccion.nombre,
                                        "sede": str(asignacion.mesa.sede), "turno": str(asignacion.turno),
                                        "fecha": fecha_limite.strftime("%d/%m/%Y")})


def crear_notificacion_traslado_autoridad(asignacion, mesa_origen):
    elector = asignacion.registro_padron.elector
    eleccion = asignacion.registro_padron.eleccion
    plantilla, _ = PlantillaNotificacion.objects.get_or_create(
        codigo="autoridad-cambio-mesa-vacante",
        defaults={
            "nombre": "Cambio de mesa de autoridad por vacante",
            "categoria": PlantillaNotificacion.Categoria.TRANSACCIONAL,
            "asunto": "Cambio de asignación de autoridad: {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "Tu asignación como autoridad para {nombre_eleccion} cambió a otra mesa de trabajo "
                "en {sede}, durante el turno {turno}. La mesa definitiva se informará cuando la "
                "elección esté en curso; tu mesa de votación no cambia.\n\nVoto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.AUTORIDAD_MESA],
            "permite_envio_manual": False,
        },
    )
    return crear_notificacion(
        plantilla=plantilla, eleccion=eleccion, elector=elector,
        contexto={"nombre_destinatario": elector.nombre_completo, "nombre_eleccion": eleccion.nombre,
                  "sede": str(asignacion.mesa.sede), "turno": str(asignacion.turno)},
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
def crear_notificaciones_ausentes_confirmadas(eleccion, fecha_limite_justificacion_electores):
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado != Eleccion.Estado.EN_CURSO:
        raise ValueError("Las notificaciones de ausentes solo se pueden confirmar durante una elección en curso.")
    if fecha_limite_justificacion_electores is None:
        raise ValueError("Debe indicar la fecha límite para presentar justificativos.")
    if fecha_limite_justificacion_electores < timezone.localdate():
        raise ValueError("La fecha límite para presentar justificativos no puede ser anterior a hoy.")
    if (
        eleccion.notificaciones_ausentes_confirmadas_en
        and eleccion.justificacion_electores_habilitada_en
    ):
        raise ValueError("Las notificaciones a ausentes ya fueron confirmadas para esta elección.")

    momento_confirmacion = timezone.now()
    if eleccion.notificaciones_ausentes_confirmadas_en:
        eleccion.justificacion_electores_habilitada_en = momento_confirmacion
        eleccion.fecha_limite_justificacion_electores = fecha_limite_justificacion_electores
        eleccion.save(
            update_fields=(
                "justificacion_electores_habilitada_en",
                "fecha_limite_justificacion_electores",
            )
        )
        return []

    mesas = Mesa.objects.filter(eleccion=eleccion)
    if not mesas.exists():
        raise ValueError("La elección no tiene mesas para verificar el cierre del escaneo.")
    if mesas.exclude(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA).exists():
        raise ValueError("Todas las mesas deben estar escaneadas y confirmadas antes de notificar a los ausentes.")

    plantilla = _plantilla_aviso_ausentes()
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
                fecha_limite_justificacion_electores=fecha_limite_justificacion_electores.strftime("%d/%m/%Y"),
            ),
        )
        for registro in registros_ausentes
    ]
    EnvioNotificacion.objects.bulk_create(envios)
    eleccion.notificaciones_ausentes_confirmadas_en = momento_confirmacion
    eleccion.justificacion_electores_habilitada_en = momento_confirmacion
    eleccion.fecha_limite_justificacion_electores = fecha_limite_justificacion_electores
    eleccion.save(
        update_fields=(
            "notificaciones_ausentes_confirmadas_en",
            "justificacion_electores_habilitada_en",
            "fecha_limite_justificacion_electores",
        )
    )
    return envios


@transaction.atomic
def actualizar_plazo_justificativos_electores(eleccion, nueva_fecha_limite):
    from apps.justificativos.models import JustificativoAusencia

    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado != Eleccion.Estado.EN_CURSO:
        raise ValueError("Solo se puede modificar el plazo durante una elección en curso.")
    if not eleccion.notificaciones_ausentes_confirmadas_en or not eleccion.justificacion_electores_habilitada_en:
        raise ValueError("El período de justificativos todavía no fue abierto.")
    if nueva_fecha_limite is None or nueva_fecha_limite < timezone.localdate():
        raise ValueError("La nueva fecha límite debe ser igual o posterior a hoy.")
    if (
        eleccion.fecha_limite_justificacion_electores
        and nueva_fecha_limite < eleccion.fecha_limite_justificacion_electores
    ):
        raise ValueError("No se puede acortar el período de justificativos.")
    if nueva_fecha_limite == eleccion.fecha_limite_justificacion_electores:
        raise ValueError("La nueva fecha límite debe ser posterior a la actual.")

    fecha_anterior = eleccion.fecha_limite_justificacion_electores
    eleccion.fecha_limite_justificacion_electores = nueva_fecha_limite
    eleccion.save(update_fields=("fecha_limite_justificacion_electores",))

    justificativos_electorales = JustificativoAusencia.objects.filter(
        registro_padron__eleccion=eleccion,
        ausencia=JustificativoAusencia.Ausencia.VOTAR,
    ).values("registro_padron_id")
    registros_ausentes = RegistroPadron.objects.filter(
        eleccion=eleccion,
        activo=True,
        asignacion_mesa__mesa__estado_escaneo=Mesa.EstadoEscaneo.PROCESADA,
        participaciones__isnull=False,
    ).exclude(pk__in=justificativos_electorales).select_related("elector").distinct()

    plantilla = _plantilla_aviso_ausentes()
    envios = [
        EnvioNotificacion(
            plantilla=plantilla,
            eleccion=eleccion,
            elector=registro.elector,
            asunto=plantilla.asunto.format(nombre_eleccion=eleccion.nombre),
            contenido=plantilla.contenido.format(
                nombre_destinatario=registro.elector.nombre_completo,
                nombre_eleccion=eleccion.nombre,
                fecha_limite_justificacion_electores=nueva_fecha_limite.strftime("%d/%m/%Y"),
            ),
        )
        for registro in registros_ausentes
    ]
    EnvioNotificacion.objects.bulk_create(envios)
    return fecha_anterior, envios


def _plantilla_aviso_ausentes():
    plantilla, _ = PlantillaNotificacion.objects.update_or_create(
        codigo="aviso-ausentes-eleccion",
        defaults={
            "nombre": "Ausentes: período de justificativos",
            "categoria": PlantillaNotificacion.Categoria.JORNADA,
            "asunto": "Información sobre tu participación: {nombre_eleccion}",
            "contenido": (
                "Hola {nombre_destinatario},\n\n"
                "En los registros de la elección {nombre_eleccion} figurás como ausente. "
                "Podés presentar un justificativo hasta el día "
                "{fecha_limite_justificacion_electores} inclusive, momento en el que finaliza "
                "el período de justificación de inasistencias electorales.\n\n"
                "Si considerás que esta información es incorrecta, comunicate con la Junta Electoral.\n\n"
                "Voto UTN"
            ),
            "roles_destinatarios": [AsignacionRol.Rol.ELECTOR],
            "permite_envio_manual": False,
        },
    )
    return plantilla


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
