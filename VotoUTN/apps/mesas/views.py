from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from apps.elecciones.models import Eleccion, EleccionClaustroDepartamento
from apps.parametros.models import Sede
from apps.usuarios.permisos import puede_administrar_elecciones


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@login_required
def gestionar_mesas(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")

    columnas_orden = {
        "claustro": "eleccion_claustro_departamento__eleccion_claustro__claustro__nombre",
        "numero": "numero",
        "departamento": "eleccion_claustro_departamento__departamento__nombre",
        "sede": "sede__nombre",
        "electores": "cantidad_electores",
        "origen": "generada_automaticamente",
    }
    ordenar = request.GET.get("ordenar", "numero")
    if ordenar not in columnas_orden:
        ordenar = "numero"
    direccion = request.GET.get("direccion", "asc")
    if direccion not in {"asc", "desc"}:
        direccion = "asc"

    mesas = eleccion.mesas.select_related(
        "sede",
        "eleccion_claustro_departamento__eleccion_claustro__claustro",
        "eleccion_claustro_departamento__departamento",
    ).annotate(cantidad_electores=Count("asignaciones_padron"))
    claustros = eleccion.elecciones_claustro.select_related("claustro").order_by("claustro__nombre")
    departamentos = (
        EleccionClaustroDepartamento.objects.filter(eleccion_claustro__eleccion=eleccion, departamento__isnull=False)
        .select_related("departamento")
        .order_by("departamento__nombre")
    )
    sedes = Sede.objects.filter(mesas__eleccion=eleccion).distinct().order_by("nombre")
    filtros = {
        "claustro": _entero(request.GET.get("claustro")),
        "departamento": _entero(request.GET.get("departamento")),
        "sede": _entero(request.GET.get("sede")),
    }
    if filtros["claustro"]:
        mesas = mesas.filter(eleccion_claustro_departamento__eleccion_claustro_id=filtros["claustro"])
        departamentos = departamentos.filter(eleccion_claustro_id=filtros["claustro"])
    if filtros["departamento"]:
        mesas = mesas.filter(eleccion_claustro_departamento__departamento_id=filtros["departamento"])
    if filtros["sede"]:
        mesas = mesas.filter(sede_id=filtros["sede"])
    opciones_departamento = {}
    for alcance in departamentos:
        opciones_departamento.setdefault(alcance.departamento_id, alcance.departamento)
    campo_orden = columnas_orden[ordenar]
    if direccion == "desc":
        campo_orden = f"-{campo_orden}"
    ordenes = [campo_orden]
    if ordenar != "numero":
        ordenes.append("numero")
    mesas = mesas.order_by(*ordenes)
    resumen = mesas.aggregate(
        total=Count("id", distinct=True),
        numero_maximo=Max("numero"),
        automaticas=Count("id", filter=Q(generada_automaticamente=True), distinct=True),
        claustros=Count(
            "eleccion_claustro_departamento__eleccion_claustro_id",
            distinct=True,
        ),
        sedes=Count("sede_id", distinct=True),
    )
    cifras_numero = len(str(resumen["numero_maximo"] or 1))
    for mesa in mesas:
        departamento = (
            mesa.eleccion_claustro_departamento.departamento
            if mesa.eleccion_claustro_departamento_id
            else None
        )
        prefijo = f"{departamento.codigo}-" if departamento else ""
        mesa.codigo_visible = f"{prefijo}{mesa.numero:0{cifras_numero}d}"
    return render(
        request,
        "mesas/gestion.html",
        {
            "eleccion": eleccion,
            "mesas": mesas,
            "resumen": resumen,
            "ordenar": ordenar,
            "direccion": direccion,
            "filtros": filtros,
            "hay_filtros": any(filtros.values()),
            "opciones_claustro": claustros,
            "opciones_departamento": list(opciones_departamento.values()),
            "opciones_sede": sedes,
            "querystring_filtros": urlencode({clave: valor for clave, valor in filtros.items() if valor}),
        },
    )
