"""Indicadores de preparación, siempre anclados a los claustros participantes."""
from collections import defaultdict

from django.db.models import Count, F, Q

from apps.autoridades.models import AsignacionAutoridad
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido, PuestoEleccion


def construir_resumen_preparacion(eleccion):
    claustros = list(eleccion.elecciones_claustro.select_related("claustro").prefetch_related("turnos_autoridad__turno"))
    sin_sede = (
        Q(asignacion_sede_padron__isnull=True)
        | Q(asignacion_sede_padron__sede__isnull=True)
        | ~Q(asignacion_sede_padron__estado="asignada")
    )
    mesa_incompatible = Q(asignacion_mesa__isnull=False) & (
        ~Q(asignacion_mesa__mesa__eleccion_id=F("eleccion_id"))
        | ~Q(asignacion_mesa__mesa__eleccion_claustro_departamento_id=F("eleccion_claustro_departamento_id"))
        | Q(asignacion_mesa__mesa__eleccion_claustro_departamento__isnull=True)
        | Q(asignacion_mesa__mesa__sede__isnull=True)
        | Q(es_principal=True, asignacion_mesa__mesa__es_especial=True)
        | Q(es_principal=False, asignacion_mesa__mesa__es_especial=False)
        | (Q(asignacion_sede_padron__sede__isnull=False)
           & ~Q(asignacion_mesa__mesa__sede_id=F("asignacion_sede_padron__sede_id")))
    )
    padrones = {
        fila["eleccion_claustro_departamento__eleccion_claustro_id"]: fila
        for fila in RegistroPadron.objects.filter(eleccion=eleccion, activo=True).order_by().values(
            "eleccion_claustro_departamento__eleccion_claustro_id",
        ).annotate(
            total=Count("pk"), sin_sede=Count("pk", filter=sin_sede),
            sin_mesa=Count("pk", filter=Q(asignacion_mesa__isnull=True)),
            incompatibles=Count("pk", filter=mesa_incompatible),
        )
    }
    mesas = defaultdict(list)
    for mesa in Mesa.objects.filter(eleccion=eleccion).order_by().annotate(
        registros_activos=Count("asignaciones_padron", filter=Q(asignaciones_padron__registro_padron__activo=True)),
    ).values("pk", "numero", "eleccion_claustro_departamento__eleccion_claustro_id", "registros_activos"):
        mesas[mesa["eleccion_claustro_departamento__eleccion_claustro_id"]].append(mesa)
    autoridades = {
        (fila["mesa_id"], fila["turno_id"]): fila["cantidad"]
        for fila in AsignacionAutoridad.objects.filter(
            mesa__eleccion=eleccion, estado="asignada", tipo="titular", registro_padron__activo=True,
            registro_padron__eleccion=eleccion,
            registro_padron__eleccion_claustro_departamento_id=F("mesa__eleccion_claustro_departamento_id"),
        ).order_by().values("mesa_id", "turno_id").annotate(cantidad=Count("registro_padron__elector_id", distinct=True))
    }
    puestos = set(PuestoEleccion.objects.filter(eleccion_claustro__eleccion=eleccion, activo=True).values_list("eleccion_claustro_id", flat=True))
    presentaciones = set(ParticipacionPartido.objects.filter(eleccion=eleccion, activa=True).values_list("eleccion_claustro_id", flat=True))
    listas = defaultdict(list)
    for lista in ListaCandidatos.objects.filter(
        participacion__eleccion=eleccion, participacion__activa=True, activa=True,
    ).values("pk", "eleccion_claustro_id", "puesto_eleccion_id", "puesto_eleccion__activo",
             "puesto_eleccion__eleccion_claustro_id", "eleccion_claustro_departamento_id",
             "puesto_eleccion__eleccion_claustro_departamento_id", "participacion__eleccion_claustro_id"):
        listas[lista["eleccion_claustro_id"]].append(lista)
    candidaturas_validas = Q(
        elector__registros_padron__eleccion=eleccion, elector__registros_padron__activo=True,
        elector__registros_padron__eleccion_claustro_departamento__eleccion_claustro_id=F("lista__eleccion_claustro_id"),
    ) & (Q(lista__eleccion_claustro_departamento__isnull=True) | Q(
        elector__registros_padron__eleccion_claustro_departamento_id=F("lista__eleccion_claustro_departamento_id"),
    )) & (Q(tipo="titular", orden__gte=1, orden__lte=F("lista__puesto_eleccion__cantidad_titulares")) | Q(
        tipo="suplente", orden__gte=1, orden__lte=F("lista__puesto_eleccion__cantidad_suplentes"),
    ))
    candidatos = {
        fila["lista_id"]: fila
        for fila in Candidato.objects.filter(lista__participacion__eleccion=eleccion, activo=True).order_by().values("lista_id").annotate(
            total=Count("pk", distinct=True), validos=Count("pk", distinct=True, filter=candidaturas_validas),
        )
    }
    resumen = {nombre: {"claustros": [], "total": len(claustros)} for nombre in ("mesas", "autoridades", "candidaturas")}
    for claustro in claustros:
        padron = padrones.get(claustro.pk, {})
        mesas_claustro = mesas[claustro.pk]
        pendientes_mesas = []
        if not padron.get("total"):
            pendientes_mesas.append("Falta cargar el padrón activo")
        if not claustro.fecha_votacion:
            pendientes_mesas.append("Falta la fecha de votación")
        if not claustro.maximo_votantes_por_mesa:
            pendientes_mesas.append("Falta el máximo por mesa")
        if not mesas_claustro:
            pendientes_mesas.append("Falta generar las mesas")
        if padron.get("sin_sede"):
            pendientes_mesas.append(f'{padron["sin_sede"]} registro{"s" if padron["sin_sede"] != 1 else ""} sin sede electoral resuelta')
        if padron.get("sin_mesa"):
            pendientes_mesas.append(f'{padron["sin_mesa"]} registro{"s" if padron["sin_mesa"] != 1 else ""} sin mesa')
        if padron.get("incompatibles"):
            pendientes_mesas.append(f'{padron["incompatibles"]} registro{"s" if padron["incompatibles"] != 1 else ""} con mesa incompatible')
        if claustro.maximo_votantes_por_mesa and any(m["registros_activos"] > claustro.maximo_votantes_por_mesa for m in mesas_claustro):
            pendientes_mesas.append("Hay mesas que superan el máximo de registros")

        pendientes_autoridades = list(pendientes_mesas)
        turnos = list(claustro.turnos_autoridad.all())
        if not turnos:
            pendientes_autoridades.append("Falta configurar los turnos")
        for configuracion in turnos:
            faltantes = sum(autoridades.get((m["pk"], configuracion.turno_id), 0) < configuracion.minimo_titulares_por_mesa for m in mesas_claustro)
            if faltantes:
                descripcion = "mesa no alcanza" if faltantes == 1 else "mesas no alcanzan"
                pendientes_autoridades.append(f"{configuracion.turno}: {faltantes} {descripcion} el mínimo de titulares")

        pendientes_candidaturas = []
        if not padron.get("total"):
            pendientes_candidaturas.append("Falta cargar el padrón activo")
        if claustro.pk not in puestos:
            pendientes_candidaturas.append("Falta habilitar puestos")
        if claustro.pk not in presentaciones:
            pendientes_candidaturas.append("Faltan presentaciones activas del claustro")
        if not listas[claustro.pk]:
            pendientes_candidaturas.append("Faltan listas activas")
        for lista in listas[claustro.pk]:
            if (not lista["puesto_eleccion_id"] or not lista["puesto_eleccion__activo"]
                or lista["puesto_eleccion__eleccion_claustro_id"] != claustro.pk
                or lista["eleccion_claustro_departamento_id"] != lista["puesto_eleccion__eleccion_claustro_departamento_id"]
                or lista["participacion__eleccion_claustro_id"] != claustro.pk):
                if "Hay listas sin puesto activo compatible con su presentación" not in pendientes_candidaturas:
                    pendientes_candidaturas.append("Hay listas sin puesto activo compatible con su presentación")
            cantidad = candidatos.get(lista["pk"], {})
            if not cantidad.get("total"):
                if "Hay listas sin candidatos activos" not in pendientes_candidaturas:
                    pendientes_candidaturas.append("Hay listas sin candidatos activos")
            elif cantidad["validos"] != cantidad["total"]:
                if "Hay candidaturas incompatibles con el padrón o el puesto" not in pendientes_candidaturas:
                    pendientes_candidaturas.append("Hay candidaturas incompatibles con el padrón o el puesto")
        for nombre, pendientes in (("mesas", pendientes_mesas), ("autoridades", pendientes_autoridades), ("candidaturas", pendientes_candidaturas)):
            resumen[nombre]["claustros"].append({"claustro": claustro.claustro, "pendientes": pendientes, "listo": not pendientes})
    for indicador in resumen.values():
        indicador["listos"] = sum(item["listo"] for item in indicador["claustros"])
        indicador["pendiente"] = not claustros or indicador["listos"] != indicador["total"]
    return resumen
