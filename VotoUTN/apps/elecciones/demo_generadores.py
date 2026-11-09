import logging
import random
from collections import Counter

from django.core.management.base import CommandError
from django.db import transaction

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustroDepartamentoSede
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import RegistroPadron, SolicitudCambioSede


logger = logging.getLogger(__name__)

OBSERVACIONES = (
    "Me mudé y la otra sede me queda más cerca.",
    "Curso la mayoría de las materias en la sede solicitada.",
    "Por razones laborales me resulta más accesible la sede solicitada.",
    "Solicito el cambio por cercanía a mi domicilio.",
)

DETALLES = {
    JustificativoAusencia.Ausencia.VOTAR: (
        "Me encontraba enfermo el día de la votación.",
        "Tuve un turno laboral que no pude reprogramar.",
        "Un inconveniente de transporte me impidió llegar.",
    ),
    JustificativoAusencia.Ausencia.AUTORIDAD: (
        "No pude presentarme como autoridad de mesa por razones de salud.",
        "Tuve un compromiso laboral impostergable el día de la elección.",
        "Un problema familiar me impidió asistir a la mesa asignada.",
    ),
}


def eleccion_actual_demo():
    eleccion = Eleccion.objects.filter(
        estado__in=(Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO),
    ).first()
    if eleccion is None:
        raise CommandError("No existe una elección publicada o en curso.")
    return eleccion


@transaction.atomic
def generar_solicitudes_demo(eleccion, cantidad=70, semilla=None):
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado != Eleccion.Estado.PUBLICADA or eleccion.autoridades_confirmadas_en:
        raise CommandError("Las solicitudes de demo requieren una elección publicada sin autoridades confirmadas.")
    aleatorio = random.Random(semilla)
    registros = RegistroPadron.objects.filter(eleccion=eleccion, activo=True).exclude(
        solicitudes_cambio_sede__isnull=False,
    ).select_related("asignacion_sede_padron", "eleccion_claustro_departamento").order_by("pk")
    sedes_por_alcance = {}
    for alcance_id, sede_id in EleccionClaustroDepartamentoSede.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro__eleccion=eleccion,
        sede__activa=True,
    ).values_list("eleccion_claustro_departamento_id", "sede_id"):
        sedes_por_alcance.setdefault(alcance_id, set()).add(sede_id)

    candidatos = []
    for registro in registros:
        asignacion = getattr(registro, "asignacion_sede_padron", None)
        origen = asignacion.sede_id if asignacion and asignacion.sede_id else registro.sede_id
        destinos = sedes_por_alcance.get(registro.eleccion_claustro_departamento_id, set()) - {origen}
        if origen and destinos:
            candidatos.append((registro, origen, destinos))
    aleatorio.shuffle(candidatos)
    autoridades = set(AsignacionAutoridad.objects.filter(
        registro_padron__eleccion=eleccion, estado=AsignacionAutoridad.Estado.ASIGNADA,
    ).values_list("registro_padron_id", flat=True))
    autoridad_con_solicitud = SolicitudCambioSede.objects.filter(
        registro_padron_id__in=autoridades,
    ).exists()
    candidato_autoridad = None
    if cantidad > 0 and not autoridad_con_solicitud:
        candidato_autoridad = next(
            (candidato for candidato in candidatos if candidato[0].pk in autoridades), None,
        )
    candidatos = [candidato for candidato in candidatos if candidato[0].pk not in autoridades]
    frecuencia = Counter(destino for candidato in candidatos for destino in candidato[2])
    if candidato_autoridad is not None:
        frecuencia.update(candidato_autoridad[2])
    sede_principal = min(frecuencia, key=lambda sede: (-frecuencia[sede], sede)) if frecuencia else None
    seleccionados = []
    if candidato_autoridad is not None:
        destinos = candidato_autoridad[2]
        destino = sede_principal if sede_principal in destinos else aleatorio.choice(sorted(destinos))
        seleccionados.append((candidato_autoridad, destino))
    principales = [candidato for candidato in candidatos if sede_principal in candidato[2]]
    otros = [candidato for candidato in candidatos if sede_principal not in candidato[2]]
    # Reservar hasta un 10 % para otras sedes, si es posible.
    principal_maximo = cantidad - cantidad // 10 - sum(destino == sede_principal for _, destino in seleccionados)
    seleccionados.extend((c, sede_principal) for c in principales[:principal_maximo])
    restantes = principales[principal_maximo:] + otros
    aleatorio.shuffle(restantes)
    for candidato in restantes[:cantidad - len(seleccionados)]:
        destinos = candidato[2]
        alternativas = destinos - {sede_principal}
        destino = aleatorio.choice(sorted(alternativas or destinos))
        seleccionados.append((candidato, destino))

    for (registro, origen, _), destino in seleccionados:
        solicitud = SolicitudCambioSede(
            registro_padron=registro,
            sede_origen_id=origen,
            sede_destino_id=destino,
            observacion=aleatorio.choice(OBSERVACIONES),
        )
        solicitud.full_clean()
        solicitud.save()
    if len(seleccionados) < cantidad:
        logger.warning(
            "Demo elección %s: se generaron %s de %s solicitudes por falta de electores elegibles.",
            eleccion.pk, len(seleccionados), cantidad,
        )
    return len(seleccionados)


@transaction.atomic
def generar_justificativos_demo(eleccion, ausencia, cantidad=2, semilla=None):
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado not in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO):
        raise CommandError("La elección debe estar publicada o en curso.")
    registros = RegistroPadron.objects.filter(eleccion=eleccion, activo=True).exclude(
        justificativos__ausencia=ausencia,
    )
    if ausencia == JustificativoAusencia.Ausencia.VOTAR:
        registros = registros.filter(participaciones__isnull=False)
    elif ausencia == JustificativoAusencia.Ausencia.AUTORIDAD:
        registros = registros.filter(asignacion_autoridad__estado=AsignacionAutoridad.Estado.ASIGNADA)
    else:
        raise ValueError("Tipo de ausencia desconocido.")
    candidatos = list(registros.distinct().order_by("pk"))
    aleatorio = random.Random(semilla)
    aleatorio.shuffle(candidatos)
    if not candidatos or cantidad == 0:
        return 0
    tipos = list(TipoJustificativo.objects.filter(activo=True))
    if not tipos:
        raise CommandError("No hay tipos de justificativo activos. Configurá al menos uno antes de continuar.")
    for registro in candidatos[:cantidad]:
        justificativo = JustificativoAusencia(
            registro_padron=registro, ausencia=ausencia,
            tipo=aleatorio.choice(tipos), detalle=aleatorio.choice(DETALLES[ausencia]),
        )
        justificativo.full_clean()
        justificativo.save()
    return min(cantidad, len(candidatos))


@transaction.atomic
def completar_justificativos_demo(eleccion, ausencia):
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    existentes = JustificativoAusencia.objects.filter(
        registro_padron__eleccion=eleccion, ausencia=ausencia,
    ).count()
    return generar_justificativos_demo(eleccion, ausencia, cantidad=max(0, 2 - existentes))
