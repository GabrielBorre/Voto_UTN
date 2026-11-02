"""Edición de un cupo sin redistribuir las autoridades del claustro."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.autoridades.distribucion import _auditar, _puede_trabajar, _registros, bloquear_edicion, es_candidato_electoral
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.mesas.models import AsignacionMesa
from apps.usuarios.permisos import puede_configurar_eleccion


def personas_disponibles(mesa, turnos):
    from apps.partidos.models import Candidato
    claustro = mesa.eleccion_claustro_departamento.eleccion_claustro
    candidatos = Candidato.objects.filter(lista__participacion__eleccion_id=mesa.eleccion_id, activo=True)
    registros = _registros(claustro).filter(
        asignacion_mesa__mesa=mesa, asignacion_autoridad__isnull=True,
    ).exclude(candidatura_autoridad__excluida=True).exclude(
        elector_id__in=candidatos.exclude(elector_id=None).values("elector_id"),
    ).exclude(elector__dni__in=candidatos.filter(elector_id=None).values("dni"))
    return [(r, [t.pk for t in turnos if _puede_trabajar(r, mesa, t, "manual")]) for r in registros]


def _validar_edicion(mesa, usuario):
    claustro = mesa.eleccion_claustro_departamento.eleccion_claustro
    if not puede_configurar_eleccion(usuario, mesa.eleccion):
        raise PermissionDenied("No tiene permiso para editar autoridades.")
    bloquear_edicion(claustro)
    return claustro


def _liberar(asignacion):
    from apps.usuarios.models import AsignacionRol, PerfilUsuario
    AsignacionRol.objects.filter(
        rol=AsignacionRol.Rol.AUTORIDAD_MESA, eleccion=asignacion.mesa.eleccion,
        mesa=asignacion.mesa,
        usuario_id__in=PerfilUsuario.objects.filter(elector_id=asignacion.registro_padron.elector_id).values("usuario_id"),
    ).delete()
    CandidaturaAutoridad.objects.filter(registro_padron_id=asignacion.registro_padron_id).update(
        mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None,
        mesa_traslado=None, turno_traslado=None,
    )
    AsignacionMesa.objects.filter(registro_padron_id=asignacion.registro_padron_id).update(autoridad_al_final=False)
    asignacion.delete()


@transaction.atomic
def asignar_manualmente(mesa, turno, registro, usuario, *, tipo, orden=None, reemplazar=None):
    from apps.autoridades.services import _crear_asignacion, _sincronizar_rol_autoridad
    claustro = _validar_edicion(mesa, usuario)
    registro = _registros(claustro).filter(pk=registro.pk, asignacion_mesa__mesa=mesa).first()
    if registro is None or es_candidato_electoral(registro):
        raise ValidationError("Seleccioná una persona elegible de esta mesa.")
    candidatura = getattr(registro, "candidatura_autoridad", None)
    if candidatura and candidatura.excluida:
        raise ValidationError("La persona está excluida de las autoridades.")
    if not _puede_trabajar(registro, mesa, turno, "manual"):
        raise ValidationError("El turno elegido se superpone con el horario de asistencia de esta persona.")
    if AsignacionAutoridad.objects.filter(registro_padron=registro).exists():
        raise ValidationError("La persona ya tiene una asignación. Quitá esa designación antes de asignarla a otro cupo.")
    config = claustro.turnos_autoridad.filter(turno=turno).first()
    if not config or tipo not in AsignacionAutoridad.Tipo.values:
        raise ValidationError("El turno o la función no están habilitados.")
    anterior = None
    if reemplazar is not None:
        anterior = AsignacionAutoridad.objects.filter(pk=reemplazar.pk, mesa=mesa, estado="asignada").first()
        if anterior is None or anterior.turno_id != turno.pk or anterior.tipo != tipo:
            raise ValidationError("La designación a reemplazar ya no corresponde a este cupo. Actualizá la mesa.")
        if tipo == "suplente":
            orden = anterior.orden_suplencia
    ocupadas = AsignacionAutoridad.objects.filter(mesa=mesa, turno=turno, tipo=tipo, estado="asignada")
    if anterior:
        ocupadas = ocupadas.exclude(pk=anterior.pk)
    limite = config.titulares_por_mesa if tipo == "titular" else config.suplentes_por_mesa
    if ocupadas.count() >= limite:
        raise ValidationError("No queda cupo para esa función y turno. Elegí una designación para reemplazar.")
    if tipo == "suplente":
        if anterior is None and AsignacionAutoridad.objects.filter(mesa=mesa, turno=turno, tipo="titular", estado="asignada").count() < config.titulares_por_mesa:
            raise ValidationError("Primero completá los titulares de esta mesa y turno.")
        usados = set(ocupadas.values_list("orden_suplencia", flat=True))
        if orden is None:
            orden = next((n for n in range(1, limite + 1) if n not in usados), None)
        if orden is None or orden < 1 or orden > limite or orden in usados:
            raise ValidationError("El lugar de suplencia no está disponible.")
    else:
        orden = None
    reemplazada = {"asignacion": anterior.pk, "registro": anterior.registro_padron_id} if anterior else None
    if anterior:
        _liberar(anterior)
    candidatura, _ = CandidaturaAutoridad.objects.get_or_create(registro_padron=registro, defaults={"cargada_por": usuario})
    candidatura.mesa_manual, candidatura.turno_manual = mesa, turno
    candidatura.tipo_manual, candidatura.orden_manual = tipo, orden
    candidatura.mesa_traslado, candidatura.turno_traslado = None, None
    candidatura.save(update_fields=("mesa_manual", "turno_manual", "tipo_manual", "orden_manual", "mesa_traslado", "turno_traslado"))
    registro.candidatura_autoridad = candidatura
    nueva = _crear_asignacion(registro, mesa, turno, usuario, tipo, orden)
    nueva.full_clean()
    nueva.save()
    AsignacionMesa.objects.filter(registro_padron=registro).update(autoridad_al_final=(tipo == "titular"))
    _sincronizar_rol_autoridad(nueva)
    _auditar(claustro, usuario, "autoridades.seleccion_manual", {
        "mesa": mesa.pk, "turno": turno.pk, "tipo": tipo, "orden": orden,
        "registro": registro.pk, "asignacion": nueva.pk, "reemplazada": reemplazada,
    })
    return nueva


@transaction.atomic
def quitar_designacion(mesa, asignacion_id, usuario):
    claustro = _validar_edicion(mesa, usuario)
    asignacion = AsignacionAutoridad.objects.filter(pk=asignacion_id, mesa=mesa, estado="asignada").first()
    if asignacion is None:
        raise ValidationError("La designación ya no está disponible en esta mesa.")
    datos = {"asignacion": asignacion.pk, "registro": asignacion.registro_padron_id,
             "mesa": mesa.pk, "turno": asignacion.turno_id, "tipo": asignacion.tipo}
    _liberar(asignacion)
    _auditar(claustro, usuario, "autoridades.designacion_quitada", datos)
