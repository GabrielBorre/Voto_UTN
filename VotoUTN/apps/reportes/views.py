from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.models import Eleccion
from apps.reportes.services import exportar_reporte_eleccion
from apps.reportes.services_pdf import (
    generar_nombre_archivo_padron,
    generar_padron_pdf,
    validar_padron_para_pdf,
)
from apps.usuarios.permisos import puede_administrar_elecciones


@login_required
def gestionar_reportes(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar reportes.")
    return render(
        request,
        "reportes/gestion.html",
        {"eleccion": eleccion, "validacion_padron_pdf": validar_padron_para_pdf(eleccion)},
    )


@login_required
def exportar_reporte(request, eleccion_id, tipo):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para exportar informacion.")
    return exportar_reporte_eleccion(eleccion, tipo)


@login_required
def generar_padron_pdf_view(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para generar el padron imprimible.")
    validacion = validar_padron_para_pdf(eleccion)
    if not validacion.apto:
        for motivo in validacion.motivos:
            messages.error(request, motivo)
        return redirect("gestionar-reportes", eleccion_id=eleccion.id)
    contenido = generar_padron_pdf(eleccion)
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{generar_nombre_archivo_padron(eleccion)}"'
    return respuesta
