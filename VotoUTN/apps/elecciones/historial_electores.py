from django.db.models import Prefetch
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.justificativos.services import estado_justificativo_electoral
from apps.padron.models import RegistroPadron


def _estado_registro(registro, momento):
    eleccion = registro.eleccion
    justificativo = next(
        (
            item
            for item in registro.justificativos.all()
            if item.ausencia == JustificativoAusencia.Ausencia.VOTAR
        ),
        None,
    )
    if eleccion.estado in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO):
        return "En Curso", "info", justificativo

    if justificativo is not None:
        etiqueta, clase = estado_justificativo_electoral(justificativo)
        return etiqueta, clase, justificativo

    participacion = bool(registro.participaciones.all())
    habilitada_en = eleccion.justificacion_electores_habilitada_en
    periodo_habilitado = habilitada_en is not None and habilitada_en <= momento
    fecha_actual = timezone.localdate(momento)
    periodo_vencido = bool(
        eleccion.fecha_limite_justificacion_electores
        and fecha_actual > eleccion.fecha_limite_justificacion_electores
    )

    if not participacion:
        return "Voto Emitido", "ok", None
    if periodo_vencido and (periodo_habilitado or eleccion.estado == Eleccion.Estado.FINALIZADA):
        return "Infractor", "danger", None
    return "En Curso - Voto No Registrado", "warn", None


def construir_historial_electoral(elector, momento=None):
    if elector is None:
        return []

    momento = momento or timezone.now()
    justificativos_elector = JustificativoAusencia.objects.filter(
        ausencia=JustificativoAusencia.Ausencia.VOTAR,
    ).order_by("-presentada_en", "-pk")
    registros = (
        RegistroPadron.objects.filter(
            elector=elector,
            eleccion__estado__in=(
                Eleccion.Estado.PUBLICADA,
                Eleccion.Estado.EN_CURSO,
                Eleccion.Estado.FINALIZADA,
            ),
        )
        .select_related(
            "eleccion",
            "eleccion_claustro_departamento__eleccion_claustro__claustro",
        )
        .prefetch_related(
            Prefetch(
                "participaciones",
                queryset=RegistroParticipacion.objects.only("pk", "registro_padron_id"),
            ),
            Prefetch("justificativos", queryset=justificativos_elector),
        )
        .order_by("-eleccion__fecha_inicio", "-eleccion_id")
    )

    historial = []
    for registro in registros:
        estado, clase, justificativo = _estado_registro(registro, momento)
        fecha_actual = timezone.localdate(momento)
        habilitada_en = registro.eleccion.justificacion_electores_habilitada_en
        periodo_habilitado = habilitada_en is not None and habilitada_en <= momento
        limite = registro.eleccion.fecha_limite_justificacion_electores
        historial.append(
            {
                "anio": registro.eleccion.fecha_inicio.year,
                "eleccion": registro.eleccion,
                "claustro": registro.eleccion_claustro_departamento.eleccion_claustro.claustro,
                "estado": estado,
                "clase_estado": clase,
                "ayuda_estado": (
                    "El período de justificación está habilitado. Puede presentar su solicitud."
                    if estado == "En Curso - Voto No Registrado"
                    and periodo_habilitado
                    and (limite is None or fecha_actual <= limite)
                    else ""
                ),
                "justificativo": justificativo,
            }
        )
    return historial
