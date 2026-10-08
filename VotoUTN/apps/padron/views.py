import csv
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.forms import FormularioPrepararClaustro
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.padron.models import ImportacionPadron
from apps.padron.forms import FormularioArchivoPadron
from apps.padron.services import PLANTILLA_PADRON_EJEMPLO, PLANTILLA_PADRON_HEADERS, confirmar_importacion, detectar_columnas_archivo, registrar_errores, validar_csv_padron
from apps.usuarios.permisos import (
    puede_administrar_elecciones,
    puede_configurar_eleccion,
    puede_importar_padron,
)


@login_required
def descargar_plantilla_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar la plantilla.")
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="plantilla_padron_{eleccion_claustro.claustro.nombre}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(PLANTILLA_PADRON_HEADERS)
    for fila in PLANTILLA_PADRON_EJEMPLO:
        escritor.writerow(fila)
    return respuesta


@login_required
def previsualizar_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para importar el padron.")
    if not puede_configurar_eleccion(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No se puede configurar el padron de una eleccion cerrada.")
    configura_padron = request.method == "POST" and "guardar-configuracion" in request.POST
    carga_archivo = request.method == "POST" and not configura_padron
    puede_configurar = puede_administrar_elecciones(request.user, eleccion_claustro.eleccion)
    puede_cargar = eleccion_claustro.eleccion.estado in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA)

    if configura_padron and not puede_configurar:
        return HttpResponseForbidden("No tiene permiso para configurar este padron.")
    if carga_archivo and not puede_cargar:
        return HttpResponseForbidden("No se puede importar un padron para una eleccion abierta o cerrada.")

    formulario_configuracion = FormularioPrepararClaustro(
        request.POST if configura_padron else None,
        instance=eleccion_claustro,
        prefix="configuracion",
    )
    formulario_archivo = FormularioArchivoPadron(
        request.POST if carga_archivo else None,
        request.FILES if carga_archivo else None,
    )
    if configura_padron and formulario_configuracion.is_valid():
        formulario_configuracion.save()
        messages.success(request, "La configuración del padrón fue guardada.")
        return redirect("previsualizar-padron", eleccion_id=eleccion_id, claustro_id=claustro_id)
    if carga_archivo and formulario_archivo.is_valid():
        archivo = formulario_archivo.cleaned_data["archivo"]
        contenido = archivo.read()
        archivo.seek(0)
        resultado = validar_csv_padron(contenido, eleccion_claustro, archivo.name)
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
    importaciones = eleccion_claustro.importaciones_padron.select_related("usuario")
    return render(
        request,
        "padron/cargar.html",
        {
            "eleccion": eleccion_claustro.eleccion,
            "claustro": eleccion_claustro,
            "formulario_configuracion": formulario_configuracion,
            "formulario_archivo": formulario_archivo,
            "importaciones": importaciones,
            "puede_configurar": puede_configurar,
            "puede_cargar": puede_cargar,
        },
    )


@login_required
def detalle_importacion_padron(request, eleccion_id, importacion_id):
    importacion = get_object_or_404(ImportacionPadron.objects.select_related("eleccion_claustro__claustro", "usuario"), pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar esta importacion.")
    importacion.archivo.open("rb")
    try:
        contenido_archivo = importacion.archivo.read()
    finally:
        importacion.archivo.close()
    columnas_detectadas = detectar_columnas_archivo(contenido_archivo, importacion.nombre_archivo)
    return render(request, "padron/detalle_importacion.html", {"eleccion": importacion.eleccion, "importacion": importacion, "columnas_detectadas": columnas_detectadas})


@login_required
def confirmar_importacion_padron(request, eleccion_id, importacion_id):
    if request.method != "POST":
        raise Http404()
    importacion = get_object_or_404(ImportacionPadron, pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para confirmar esta importacion.")
    if not puede_configurar_eleccion(request.user, importacion.eleccion):
        return HttpResponseForbidden("No se puede confirmar una importacion para una eleccion cerrada.")
    if importacion.estado != ImportacionPadron.Estado.PREVISUALIZADA:
        messages.error(request, "Solo se pueden confirmar importaciones sin errores.")
        return redirect("detalle-importacion-padron", eleccion_id=eleccion_id, importacion_id=importacion.id)
    try:
        cantidad = confirmar_importacion(importacion)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        cantidad_existente = max(importacion.cantidad_validas - cantidad, 0)
        messages.success(
            request,
            f"Padron confirmado. Filas procesadas: {importacion.cantidad_validas}. "
            f"Nuevos: {cantidad}. Ya existentes: {cantidad_existente}.",
        )
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
