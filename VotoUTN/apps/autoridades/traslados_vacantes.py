"""Propuestas de traslado para cubrir vacantes antes de la jornada."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.padron.models import RegistroPadron
from apps.usuarios.permisos import puede_administrar_elecciones


def candidatos_para_vacante(ausente):
    """Autoridades de la misma sede, alcance y turno cuya mesa conserva un titular."""
    from apps.partidos.models import Candidato
    if (ausente.estado != AsignacionAutoridad.Estado.RECHAZADA or ausente.reemplazo_confirmado_en
            or ausente.registro_padron.eleccion.estado != Eleccion.Estado.PUBLICADA
            or not ausente.registro_padron.eleccion.autoridades_confirmadas_en
            or RegistroPadron.objects.filter(eleccion_id=ausente.registro_padron.eleccion_id, qr_generado_en__isnull=False).exists()
            or not JustificativoAusencia.objects.filter(
                registro_padron=ausente.registro_padron,
                ausencia=JustificativoAusencia.Ausencia.AUTORIDAD,
                estado=JustificativoAusencia.Estado.APROBADO,
            ).exists()):
        return AsignacionAutoridad.objects.none()
    config = ausente.mesa.eleccion_claustro_departamento.eleccion_claustro.turnos_autoridad.filter(turno=ausente.turno).first()
    if not config or AsignacionAutoridad.objects.filter(
        mesa=ausente.mesa, turno=ausente.turno, tipo="titular", estado="asignada",
    ).count() >= config.titulares_por_mesa:
        return AsignacionAutoridad.objects.none()
    candidaturas = Candidato.objects.filter(lista__participacion__eleccion=ausente.registro_padron.eleccion, activo=True)
    return AsignacionAutoridad.objects.filter(
        mesa__eleccion_claustro_departamento=ausente.mesa.eleccion_claustro_departamento,
        mesa__sede=ausente.mesa.sede, turno=ausente.turno,
        tipo="titular", estado="asignada", registro_padron__activo=True,
    ).exclude(mesa=ausente.mesa).exclude(candidatura__excluida=True).exclude(
        registro_padron__elector_id__in=candidaturas.exclude(elector_id=None).values("elector_id"),
    ).exclude(
        registro_padron__elector__dni__in=candidaturas.filter(elector_id=None).values("dni"),
    ).exclude(
        registro_padron__sede__isnull=False, registro_padron__turno_cursada__isnull=True,
    ).exclude(
        registro_padron__turno_cursada__hora_inicio__lt=ausente.turno.hora_fin,
        registro_padron__turno_cursada__hora_fin__gt=ausente.turno.hora_inicio,
    ).annotate(
        titulares_origen=Count("mesa__autoridades", filter=Q(
            mesa__autoridades__turno=ausente.turno,
            mesa__autoridades__tipo="titular", mesa__autoridades__estado="asignada",
        ), distinct=True),
    ).filter(titulares_origen__gt=config.minimo_titulares_por_mesa).select_related(
        "mesa__sede", "registro_padron__elector", "registro_padron__turno_cursada", "candidatura",
    ).order_by("mesa__numero", "registro_padron__elector__apellido", "registro_padron__elector__nombre", "pk")


@transaction.atomic
def confirmar_traslado_por_vacante(ausente, candidato_id, usuario):
    from apps.autoridades.distribucion import _auditar, es_candidato_electoral
    from apps.notificaciones.services import crear_notificacion_traslado_autoridad, enviar_notificacion
    from apps.usuarios.models import AsignacionRol, PerfilUsuario

    eleccion = Eleccion.objects.select_for_update().get(pk=ausente.registro_padron.eleccion_id)
    if eleccion.estado != Eleccion.Estado.PUBLICADA or not eleccion.autoridades_confirmadas_en or not puede_administrar_elecciones(usuario, eleccion):
        raise PermissionDenied("El traslado solo puede confirmarlo la Junta con la elección publicada.")
    actual = AsignacionAutoridad.objects.select_for_update(of=("self",)).select_related(
        "registro_padron__eleccion", "mesa__eleccion_claustro_departamento__eleccion_claustro", "mesa__sede", "turno",
    ).get(pk=ausente.pk)
    candidato = candidatos_para_vacante(actual).filter(pk=candidato_id).first()
    if candidato is None or es_candidato_electoral(candidato.registro_padron):
        raise ValidationError("La propuesta ya no está disponible. Actualizá la cobertura y elegí otra persona.")
    candidato = AsignacionAutoridad.objects.select_for_update(of=("self",)).select_related(
        "registro_padron__elector", "mesa__sede", "candidatura", "turno",
    ).get(pk=candidato.pk)
    if candidato.candidatura_id and candidato.candidatura.excluida:
        raise ValidationError("La persona seleccionada ya no está disponible.")
    origen = candidato.mesa
    candidatura = candidato.candidatura
    if candidatura and candidatura.mesa_manual_id:
        candidatura.mesa_manual = actual.mesa
        candidatura.turno_manual = actual.turno
    if candidatura and candidatura.mesa_traslado_id:
        candidatura.mesa_traslado = actual.mesa
        candidatura.turno_traslado = actual.turno
    if candidatura:
        candidatura.save(update_fields=("mesa_manual", "turno_manual", "mesa_traslado", "turno_traslado"))
    candidato.mesa = actual.mesa
    candidato.full_clean()
    candidato.save(update_fields=("mesa",))
    actual.reemplazada_por = candidato
    actual.reemplazo_confirmado_en = timezone.now()
    actual.reemplazo_confirmado_por = usuario
    actual.save(update_fields=("reemplazada_por", "reemplazo_confirmado_en", "reemplazo_confirmado_por"))
    perfil = PerfilUsuario.objects.filter(elector=candidato.registro_padron.elector, activo=True).first()
    if perfil:
        AsignacionRol.objects.filter(usuario=perfil.usuario, rol=AsignacionRol.Rol.AUTORIDAD_MESA,
                                     eleccion=eleccion, mesa=origen).delete()
        AsignacionRol.objects.get_or_create(usuario=perfil.usuario, rol=AsignacionRol.Rol.AUTORIDAD_MESA,
                                             eleccion=eleccion, mesa=actual.mesa, sede=actual.mesa.sede)
    _auditar(actual.mesa.eleccion_claustro_departamento.eleccion_claustro, usuario,
             "autoridades.traslado_por_vacante", {"ausente": actual.pk, "asignacion": candidato.pk,
                                                   "mesa_origen": origen.pk, "mesa_destino": actual.mesa_id})
    envio = crear_notificacion_traslado_autoridad(candidato, origen)
    transaction.on_commit(lambda: enviar_notificacion(envio))
    return candidato
