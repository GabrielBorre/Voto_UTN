"""Indicadores de participación para el tablero de escritorio de una elección."""
from dataclasses import dataclass

from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import ROLES_CON_PARTICIPACION


ESTADOS_ESCANEO = tuple(Mesa.EstadoEscaneo.values)


@dataclass(frozen=True)
class FiltrosDashboard:
    claustro_id: int | None = None
    sede_id: int | None = None
    departamento_id: int | None = None
    escaneo: str = ""

    @classmethod
    def desde_parametros(cls, parametros):
        escaneo = parametros.get("escaneo", "")
        return cls(
            claustro_id=_entero(parametros.get("claustro")),
            sede_id=_entero(parametros.get("sede")),
            departamento_id=_entero(parametros.get("departamento")),
            escaneo=escaneo if escaneo in ESTADOS_ESCANEO else "",
        )


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _porcentaje(parte, total):
    return round(parte * 100 / total, 1) if total else 0


def seleccionar_eleccion_actual(elecciones, eleccion_id=None):
    """Prefiere la elección pedida; luego la que está en curso; luego la más reciente."""
    elecciones = elecciones.order_by("-fecha_inicio", "-id")
    pedida = _entero(eleccion_id)
    if pedida is not None:
        elegida = elecciones.filter(pk=pedida).first()
        if elegida is not None:
            return elegida
    hoy = timezone.localdate()
    return elecciones.filter(fecha_inicio__lte=hoy, fecha_fin__gte=hoy).first() or elecciones.first()


def _mesas_del_alcance(usuario, eleccion):
    """Replica el alcance de puede_registrar_participacion para no mostrar mesas ajenas."""
    mesas = Mesa.objects.filter(eleccion=eleccion)
    es_administrador_sistema = AsignacionRol.objects.filter(
        usuario=usuario, activo=True, rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA
    ).exists()
    if usuario.is_superuser or es_administrador_sistema:
        return mesas, False
    asignaciones = AsignacionRol.objects.filter(
        usuario=usuario, activo=True, rol__in=ROLES_CON_PARTICIPACION, eleccion=eleccion
    )
    if asignaciones.filter(sede__isnull=True, mesa__isnull=True).exists():
        return mesas, False
    sedes = asignaciones.filter(mesa__isnull=True, sede__isnull=False).values("sede")
    mesas_asignadas = asignaciones.filter(mesa__isnull=False).values("mesa")
    return mesas.filter(Q(pk__in=mesas_asignadas) | Q(sede__in=sedes)), True


def _registros_filtrados(eleccion, filtros, mesas_alcance, restringido):
    registros = RegistroPadron.objects.filter(eleccion=eleccion, activo=True)
    if restringido:
        registros = registros.filter(asignacion_mesa__mesa__in=mesas_alcance)
    if filtros.claustro_id:
        registros = registros.filter(eleccion_claustro_departamento__eleccion_claustro__claustro_id=filtros.claustro_id)
    if filtros.departamento_id:
        registros = registros.filter(eleccion_claustro_departamento__departamento_id=filtros.departamento_id)
    if filtros.sede_id:
        registros = registros.filter(sede_id=filtros.sede_id)
    return registros


def _electores_de_mesas_procesadas(registros):
    """Base de las métricas: en mesas sin confirmar todavía no se sabe quién votó."""
    return registros.filter(asignacion_mesa__mesa__estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)


def _mesas_filtradas(mesas, filtros):
    if filtros.claustro_id:
        mesas = mesas.filter(eleccion_claustro_departamento__eleccion_claustro__claustro_id=filtros.claustro_id)
    if filtros.departamento_id:
        mesas = mesas.filter(eleccion_claustro_departamento__departamento_id=filtros.departamento_id)
    if filtros.sede_id:
        mesas = mesas.filter(sede_id=filtros.sede_id)
    return mesas


MAXIMO_ELECCIONES_HISTORIAL = 12


def _elecciones_para_historial(usuario):
    elecciones = Eleccion.objects.all()
    es_administrador_sistema = AsignacionRol.objects.filter(
        usuario=usuario, activo=True, rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA
    ).exists()
    if usuario.is_superuser or es_administrador_sistema:
        return elecciones
    return elecciones.filter(
        asignaciones_rol__usuario=usuario,
        asignaciones_rol__activo=True,
        asignaciones_rol__rol__in=ROLES_CON_PARTICIPACION,
    ).distinct()


def _historial_entre_elecciones(usuario, filtros):
    """Porcentaje de participación final de cada elección, de la más antigua a la más reciente."""
    elecciones = list(_elecciones_para_historial(usuario).order_by("fecha_inicio", "id"))
    etiquetas, porcentajes, participaron, totales = [], [], [], []
    for eleccion in elecciones[-MAXIMO_ELECCIONES_HISTORIAL:]:
        mesas, restringido = _mesas_del_alcance(usuario, eleccion)
        registros = _registros_filtrados(eleccion, filtros, mesas, restringido)
        base = _electores_de_mesas_procesadas(registros)
        total = base.count()
        if not total:
            continue
        # Un QR escaneado (con participación) es un elector que no votó.
        cantidad = total - base.filter(participaciones__isnull=False).count()
        etiquetas.append(eleccion.nombre)
        porcentajes.append(_porcentaje(cantidad, total))
        participaron.append(cantidad)
        totales.append(total)
    return {"etiquetas": etiquetas, "porcentajes": porcentajes, "participaron": participaron, "totales": totales}


def opciones_filtros(eleccion):
    return {
        "claustros": Claustro.objects.filter(elecciones_claustro__eleccion=eleccion).distinct(),
        "sedes": Sede.objects.filter(elecciones_sede__eleccion=eleccion).distinct(),
        "departamentos": Departamento.objects.filter(
            elecciones_claustro_departamento__eleccion_claustro__eleccion=eleccion
        ).distinct(),
    }


def construir_dashboard(usuario, eleccion, filtros):
    mesas_alcance, restringido = _mesas_del_alcance(usuario, eleccion)
    registros = _registros_filtrados(eleccion, filtros, mesas_alcance, restringido)
    mesas = _mesas_filtradas(mesas_alcance, filtros)

    total_electores = registros.count()
    electores_base_qs = _electores_de_mesas_procesadas(registros)
    electores_base = electores_base_qs.count()
    # Un QR escaneado (con participación) es un elector que no votó.
    ausentes = electores_base_qs.filter(participaciones__isnull=False)
    total_ausentes = ausentes.count()
    participaron = electores_base - total_ausentes

    mesas_anotadas = (
        mesas.select_related("sede", "eleccion_claustro_departamento__eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento")
        .annotate(
            cantidad_electores=Count(
                "asignaciones_padron",
                filter=Q(asignaciones_padron__registro_padron__activo=True),
                distinct=True,
            ),
            cantidad_participaron=Count(
                "participaciones",
                filter=Q(participaciones__registro_padron__activo=True),
                distinct=True,
            ),
        )
        .order_by("sede__nombre", "numero")
    )
    total_mesas = mesas.count()
    mesas_escaneadas = mesas.filter(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA).count()
    if filtros.escaneo:
        mesas_anotadas = mesas_anotadas.filter(estado_escaneo=filtros.escaneo)

    justificativos = JustificativoAusencia.objects.filter(registro_padron=OuterRef("pk"))
    justificativos_recibidos = ausentes.filter(Exists(justificativos)).count()
    justificativos_confirmados = ausentes.filter(
        Exists(justificativos.filter(estado=JustificativoAusencia.Estado.APROBADO))
    ).count()

    # La columna Votaron solo se completa cuando la mesa fue procesada.
    mesas_lista = list(mesas_anotadas)
    for mesa in mesas_lista:
        mesa.cantidad_votaron = mesa.cantidad_electores - mesa.cantidad_participaron

    return {
        "mesas_total": total_mesas,
        "mesas_escaneadas": mesas_escaneadas,
        "mesas_escaneadas_pct": _porcentaje(mesas_escaneadas, total_mesas),
        "mesas": mesas_lista,
        "electores_total": total_electores,
        "electores_en_mesas_escaneadas": electores_base,
        "electores_participaron": participaron,
        "electores_participaron_pct": _porcentaje(participaron, electores_base),
        "electores_ausentes": total_ausentes,
        "justificativos_recibidos": justificativos_recibidos,
        "justificativos_recibidos_pct": _porcentaje(justificativos_recibidos, total_ausentes),
        "justificativos_confirmados": justificativos_confirmados,
        "justificativos_confirmados_pct": _porcentaje(justificativos_confirmados, justificativos_recibidos),
        "historial": _historial_entre_elecciones(usuario, filtros),
    }
