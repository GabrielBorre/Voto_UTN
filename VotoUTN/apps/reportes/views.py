from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from apps.elecciones.models import Eleccion
from apps.reportes.services import exportar_reporte_eleccion
from apps.usuarios.permisos import puede_administrar_elecciones


@login_required
def gestionar_reportes(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar reportes.")
    return render(request, "elecciones/reportes.html", {"eleccion": eleccion})


@login_required
def exportar_reporte(request, eleccion_id, tipo):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para exportar informacion.")
    return exportar_reporte_eleccion(eleccion, tipo)
