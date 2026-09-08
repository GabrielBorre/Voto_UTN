import csv
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.padron.models import ImportacionPadron
from apps.padron.forms import FormularioArchivoPadron
from apps.padron.services import CABECERAS_PADRON, confirmar_importacion, registrar_errores, validar_csv_padron
from apps.usuarios.permisos import puede_importar_padron


@login_required
def descargar_plantilla_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar la plantilla.")
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="plantilla_padron_{eleccion_claustro.claustro.nombre}.csv"'
    respuesta.write("\ufeff")
    csv.writer(respuesta).writerow(CABECERAS_PADRON)
    return respuesta


@login_required
def previsualizar_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para importar el padron.")
    if eleccion_claustro.eleccion.estado not in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA):
        return HttpResponseForbidden("No se puede importar un padron para una eleccion abierta o cerrada.")
    formulario = FormularioArchivoPadron(request.POST or None, request.FILES or None)
    if request.method == "POST" and formulario.is_valid():
        archivo = formulario.cleaned_data["archivo"]
        contenido = archivo.read()
        archivo.seek(0)
        resultado = validar_csv_padron(contenido, eleccion_claustro)
        importacion = ImportacionPadron.objects.create(
            eleccion=eleccion_claustro.eleccion,
            eleccion_claustro=eleccion_claustro,
            archivo=archivo,
            nombre_archivo=archivo.name,
            huella_archivo=hashlib.sha256(contenido).hexdigest(),
            cantidad_filas=len(resultado.filas),
            cantidad_validas=len(resultado.filas) if not resultado.errores else 0,
            cantidad_errores=len(resultado.errores),
            estado=ImportacionPadron.Estado.PREVISUALIZADA if not resultado.errores else ImportacionPadron.Estado.RECHAZADA,
            usuario=request.user,
        )
        registrar_errores(importacion, resultado.errores)
        return redirect("detalle-importacion-padron", eleccion_id=eleccion_id, importacion_id=importacion.id)
    return render(request, "padron/cargar.html", {"eleccion": eleccion_claustro.eleccion, "claustro": eleccion_claustro, "formulario": formulario})


@login_required
def detalle_importacion_padron(request, eleccion_id, importacion_id):
    importacion = get_object_or_404(ImportacionPadron.objects.select_related("eleccion_claustro__claustro", "usuario"), pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar esta importacion.")
    return render(request, "padron/detalle_importacion.html", {"eleccion": importacion.eleccion, "importacion": importacion})


@login_required
def confirmar_importacion_padron(request, eleccion_id, importacion_id):
    if request.method != "POST":
        raise Http404()
    importacion = get_object_or_404(ImportacionPadron, pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para confirmar esta importacion.")
    if importacion.estado != ImportacionPadron.Estado.PREVISUALIZADA:
        messages.error(request, "Solo se pueden confirmar importaciones sin errores.")
        return redirect("detalle-importacion-padron", eleccion_id=eleccion_id, importacion_id=importacion.id)
    try:
        cantidad = confirmar_importacion(importacion)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Padron confirmado. Se incorporaron {cantidad} registros nuevos.")
    return redirect("detalle-importacion-padron", eleccion_id=eleccion_id, importacion_id=importacion.id)


@login_required
def descargar_errores_importacion(request, eleccion_id, importacion_id):
    importacion = get_object_or_404(ImportacionPadron, pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar los errores.")
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="errores_padron_{importacion.id}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(("fila", "campo", "mensaje"))
    for error in importacion.errores.all():
        escritor.writerow((error.fila or "", error.campo, error.mensaje))
    return respuesta


@login_required
def historial_importaciones_padron(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_importar_padron(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar el historial de padrones.")
    importaciones = eleccion.importaciones_padron.select_related("eleccion_claustro__claustro", "usuario")
    return render(request, "padron/historial_importaciones.html", {"eleccion": eleccion, "importaciones": importaciones})
