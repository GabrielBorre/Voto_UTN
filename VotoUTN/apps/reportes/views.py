from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.padron.services import registrar_emision_padron_imprimible
from apps.reportes.services import exportar_reporte_eleccion
from apps.reportes.services_pdf import (
    generar_nombre_archivo_padron,
    generar_padron_pdf,
    validar_padron_para_pdf,
)
from apps.reportes.services_boletas_pdf import (
    generar_boletas_pdf,
    generar_nombre_archivo_boletas,
    validar_boletas_pdf,
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
        {
            "eleccion": eleccion,
            "validacion_padron_pdf": validar_padron_para_pdf(eleccion),
            "validacion_boletas_pdf": validar_boletas_pdf(eleccion),
            "puede_exportar_infractores": eleccion.estado == Eleccion.Estado.CERRADA
            and not JustificativoAusencia.objects.filter(
                registro_padron__eleccion=eleccion,
                estado=JustificativoAusencia.Estado.PENDIENTE,
            ).exists(),
        },
    )


@login_required
def exportar_reporte(request, eleccion_id, tipo):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para exportar informacion.")
    if tipo == "infractores":
        if eleccion.estado != Eleccion.Estado.CERRADA:
            return HttpResponseForbidden("La exportación de infractores solo está disponible para elecciones finalizadas.")
        if JustificativoAusencia.objects.filter(
            registro_padron__eleccion=eleccion,
            estado=JustificativoAusencia.Estado.PENDIENTE,
        ).exists():
            return HttpResponseForbidden("No se puede exportar infractores con justificativos pendientes de resolución.")
    return exportar_reporte_eleccion(eleccion, tipo)


@login_required
@transaction.atomic
def generar_padron_pdf_view(request, eleccion_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion.objects.select_for_update(), pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para generar el padron imprimible.")
    validacion = validar_padron_para_pdf(eleccion)
    if not validacion.apto:
        for motivo in validacion.motivos:
            messages.error(request, motivo)
        return redirect("gestionar-reportes", eleccion_id=eleccion.id)
    contenido = generar_padron_pdf(eleccion)
    registrar_emision_padron_imprimible(eleccion, request.user)
    messages.success(request, "Padrón imprimible emitido. Los cambios de sede y de QR quedan bloqueados.")
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{generar_nombre_archivo_padron(eleccion)}"'
    return respuesta


@login_required
def generar_boletas_pdf_view(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para generar las boletas electorales.")
    validacion = validar_boletas_pdf(eleccion)
    if not validacion.apto:
        for motivo in validacion.motivos:
            messages.error(request, motivo)
        return redirect("gestionar-reportes", eleccion_id=eleccion.id)
    contenido = generar_boletas_pdf(eleccion)
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{generar_nombre_archivo_boletas(eleccion)}"'
    return respuesta
