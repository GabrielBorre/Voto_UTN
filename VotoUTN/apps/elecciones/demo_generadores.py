import logging
import random

from django.core.management.base import CommandError
from django.db import transaction

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import RegistroPadron


logger = logging.getLogger(__name__)

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
def generar_solicitudes_demo(eleccion):
    from apps.padron.solicitudes_escenario import (
        crear_solicitudes_escenario, seleccionar_solicitudes_publicacion,
    )

    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado != Eleccion.Estado.PUBLICADA or eleccion.autoridades_confirmadas_en:
        raise CommandError("Las solicitudes de demo requieren una elección publicada sin autoridades confirmadas.")
    planes = seleccionar_solicitudes_publicacion(eleccion)
    if not planes:
        return 0
    resultado = crear_solicitudes_escenario(eleccion, planes)
    return len(resultado["creadas"])


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
