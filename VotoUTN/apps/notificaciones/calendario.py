"""Materialización transaccional de los mensajes del calendario."""
from django.conf import settings
from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from apps.elecciones.models import Eleccion
from apps.padron.models import RegistroPadron
from apps.usuarios.models import AsignacionRol
from .models import MensajeProgramado, PlantillaNotificacion
from .services import crear_notificacion, procesar_envios_pendientes


def destinatarios(programacion):
    fecha, plantilla = programacion.fecha_administrativa, programacion.plantilla
    roles = set(fecha.roles_destinatarios) & set(plantilla.roles_destinatarios)
    registros = RegistroPadron.objects.filter(eleccion=programacion.eleccion, activo=True).select_related("elector", "sede")
    if not fecha.alcance_todos_claustros:
        registros = registros.filter(eleccion_claustro_departamento__eleccion_claustro__claustro__in=fecha.claustros.all())
    if plantilla.claustros.exists():
        registros = registros.filter(eleccion_claustro_departamento__eleccion_claustro__claustro__in=plantilla.claustros.all())
    criterio = fecha.criterio_destinatarios
    if criterio == "electores_ausentes_confirmados":
        registros = registros.filter(participaciones__isnull=False, asignacion_mesa__mesa__estado_escaneo="procesada")
        if not programacion.eleccion.notificaciones_ausentes_confirmadas_en:
            raise ValueError("Todavía no se confirmó el escaneo de ausentes de la elección.")
    elif criterio == "autoridades_asignadas":
        registros = registros.filter(asignacion_autoridad__isnull=False).exclude(asignacion_autoridad__estado="rechazada")
    elif criterio == "autoridades_ausentes_confirmadas":
        # Rechazar una designación no prueba una ausencia en la jornada.
        registros = registros.filter(asignacion_autoridad__isnull=False,
                                     justificativos__ausencia="autoridad", justificativos__estado="aprobado")
    if "elector" not in roles:
        registros = registros.filter(asignacion_autoridad__isnull=False) if "autoridad_mesa" in roles else registros.none()
    vistos = set()
    for registro in registros.distinct():
        if registro.elector_id not in vistos:
            vistos.add(registro.elector_id)
            yield registro.elector, None, registro
    roles_junta = roles & {"administrador_junta", "administrativo_junta"}
    asignaciones = AsignacionRol.objects.filter(activo=True, usuario__is_active=True, rol__in=roles_junta).filter(Q(eleccion=programacion.eleccion) | Q(eleccion__isnull=True)).select_related("usuario")
    for claustros in ([fecha.claustros.all()] if not fecha.alcance_todos_claustros else []) + ([plantilla.claustros.all()] if plantilla.claustros.exists() else []):
        asignaciones = asignaciones.filter(Q(mesa__isnull=True) | Q(mesa__eleccion_claustro_departamento__eleccion_claustro__claustro__in=claustros))
    usuarios = set()
    for asignacion in asignaciones:
        if asignacion.usuario_id not in usuarios:
            usuarios.add(asignacion.usuario_id)
            yield None, asignacion.usuario, None


def contexto_mensaje(programacion, elector, usuario, registro):
    contexto = {}
    contexto.update(nombre_destinatario=elector.nombre_completo if elector else usuario.get_full_name() or usuario.username,
                    nombre_eleccion=programacion.eleccion.nombre, nombre_fecha_administrativa=programacion.fecha_administrativa.nombre)
    contexto["url_accion"] = settings.VOTO_PUBLIC_URL.rstrip("/") + reverse("inicio-autenticado")
    if registro:
        asignacion = getattr(registro, "asignacion_mesa", None)
        autoridad = getattr(registro, "asignacion_autoridad", None)
        if asignacion:
            contexto.update(mesa=asignacion.mesa.codigo, sede=asignacion.mesa.sede.nombre)
        elif registro.sede_id:
            contexto["sede"] = registro.sede.nombre
        claustro = registro.eleccion_claustro_departamento.eleccion_claustro
        contexto["claustros"] = str(claustro.claustro)
        contexto["fecha_votacion"] = claustro.fecha_votacion.strftime("%d/%m/%Y") if claustro.fecha_votacion else "A confirmar"
        if autoridad:
            contexto.update(turno=str(autoridad.turno), horario_turno=f"{autoridad.turno.hora_inicio:%H:%M} - {autoridad.turno.hora_fin:%H:%M}")
            if "elector" not in programacion.plantilla.roles_destinatarios:
                contexto.update(mesa=autoridad.mesa.codigo, sede=autoridad.mesa.sede.nombre)
    # Las fechas de envío no son plazos de trámites ni fechas de capacitación.
    # No completar esas variables con datos inventados.
    from string import Formatter
    requeridas = {campo for _, campo, _, _ in Formatter().parse(programacion.plantilla.asunto + programacion.plantilla.contenido) if campo}
    faltantes = requeridas - contexto.keys()
    if faltantes:
        raise ValueError("La plantilla requiere datos no disponibles en el calendario: " + ", ".join(sorted(faltantes)))
    return contexto


def procesar_calendario():
    cantidad = 0
    ids = list(MensajeProgramado.objects.filter(habilitado=True, procesado_en__isnull=True, programado_para__lte=timezone.now()).values_list("pk", "eleccion_id"))
    for pk, eleccion_id in ids:
        try:
            with transaction.atomic():
                eleccion = Eleccion.objects.select_for_update().get(pk=eleccion_id)
                programacion = MensajeProgramado.objects.select_for_update().select_related("fecha_administrativa", "plantilla", "eleccion").get(pk=pk)
                if not programacion.habilitado or programacion.procesado_en or programacion.programado_para > timezone.now():
                    continue
                estados = list(Eleccion.Estado.values)
                if estados.index(eleccion.estado) < estados.index(programacion.estado_eleccion):
                    continue
                if not programacion.plantilla.activa:
                    raise ValueError("La plantilla está inactiva. Seleccione una plantilla activa.")
                for elector, usuario, registro in destinatarios(programacion):
                    crear_notificacion(plantilla=programacion.plantilla, eleccion=eleccion, elector=elector, destinatario=usuario,
                                       contexto=contexto_mensaje(programacion, elector, usuario, registro))
                programacion.procesado_en = timezone.now()
                programacion.error = ""
                programacion.save(update_fields=("procesado_en", "error"))
                cantidad += 1
        except Exception as error:
            MensajeProgramado.objects.filter(pk=pk, procesado_en__isnull=True).update(error=str(error)[:1000])
    procesar_envios_pendientes()
    return cantidad
