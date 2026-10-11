from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_administrar_elecciones


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
        },
    )
