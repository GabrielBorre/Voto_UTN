import csv
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.forms import FormularioPrepararClaustro
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.padron.models import (
    AsignacionSedePadron,
    ConfiguracionSedesClaustro,
    ImportacionPadron,
    ReglaSedeClaustro,
)
from apps.padron.forms import FormularioArchivoPadron, FormularioReglaSedeClaustro
from apps.padron.services import (
    PLANTILLA_PADRON_EJEMPLO,
    PLANTILLA_PADRON_HEADERS,
    alcances_con_sedes_multiples,
    calcular_asignaciones_sede_claustro,
    confirmar_importacion,
    detectar_columnas_archivo,
    eliminar_padron_claustro as servicio_eliminar_padron_claustro,
    estado_eliminacion_padron_claustro,
    invalidar_asignaciones_sede_claustro,
    invalidar_calculo_padrones_votacion,
    registrar_errores,
    validar_csv_padron,
)
from apps.usuarios.permisos import puede_administrar_elecciones, puede_importar_padron
from apps.padron.models import RegistroPadron
from apps.padron.services import calcular_mesas_automaticas_eleccion, claustro_tiene_emision_vigente


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
        return HttpResponseForbidden("No tiene permiso para importar el padrón.")
    configura_padron = request.method == "POST" and "guardar-configuracion" in request.POST
    carga_archivo = request.method == "POST" and not configura_padron
    autoguardado = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.POST.get("autoguardado") == "1"
    puede_configurar = puede_administrar_elecciones(request.user, eleccion_claustro.eleccion)
    puede_cargar = eleccion_claustro.eleccion.estado in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA)

    if configura_padron and not puede_configurar:
        return HttpResponseForbidden("No tiene permiso para configurar este padrón.")
    if carga_archivo and not puede_cargar:
        return HttpResponseForbidden("No se puede importar un padrón para una elección abierta o cerrada.")

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
        cambio_maximo = "maximo_votantes_por_mesa" in formulario_configuracion.changed_data
        formulario_configuracion.save()
        mensaje_mesas = None
        if cambio_maximo:
            try:
                resultado_mesas = calcular_mesas_automaticas_eleccion(
                    eleccion_claustro.eleccion,
                    usuario=request.user,
                    request=request,
                )
            except ValueError as error:
                mensaje_mesas = f"Configuración guardada; las mesas no se recalcularon: {error}"
            else:
                mensaje_mesas = (
                    f"Mesas recalculadas automáticamente: {resultado_mesas['mesas']} mesas "
                    f"para {resultado_mesas['electores']} electores."
                )
        if autoguardado:
            return JsonResponse({"mensaje": mensaje_mesas or "Configuración guardada automáticamente."})
        if mensaje_mesas:
            if "no se recalcularon" in mensaje_mesas:
                messages.warning(request, mensaje_mesas)
            else:
                messages.success(request, mensaje_mesas)
        else:
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
    cantidad_registros_padron = RegistroPadron.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).count()
    cantidad_electores_padron = RegistroPadron.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).values("elector_id").distinct().count()
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
            "cantidad_registros_padron": cantidad_registros_padron,
            "cantidad_electores_padron": cantidad_electores_padron,
            "puede_eliminar_padron": puede_configurar and puede_cargar and cantidad_registros_padron > 0,
            "emision_vigente": claustro_tiene_emision_vigente(eleccion_claustro),
        },
        status=422 if configura_padron and autoguardado else 200,
    )


@login_required
def eliminar_padron_claustro(request, eleccion_id, claustro_id):
    claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    if not puede_administrar_elecciones(request.user, claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para eliminar el padrón del claustro.")

    resumen = estado_eliminacion_padron_claustro(claustro)
    if request.method == "POST":
        try:
            resumen = servicio_eliminar_padron_claustro(claustro, request.user, request=request)
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("eliminar-padron-claustro", eleccion_id=eleccion_id, claustro_id=claustro_id)
        messages.success(
            request,
            f"Se eliminaron {resumen['cantidad_registros']} registros del padrón. "
            f"Se liberaron {resumen['cantidad_electores_a_eliminar']} identidades sin otras referencias; "
            "se conservaron las vinculadas a otros padrones o datos históricos. "
            "El historial de importaciones permanece.",
        )
        return redirect("previsualizar-padron", eleccion_id=eleccion_id, claustro_id=claustro_id)

    return render(request, "padron/confirmar_eliminar_padron.html", {
        "eleccion": claustro.eleccion,
        "claustro": claustro,
        "resumen": resumen,
    })


@login_required
def detalle_importacion_padron(request, eleccion_id, importacion_id):
    importacion = get_object_or_404(ImportacionPadron.objects.select_related("eleccion_claustro__claustro", "usuario"), pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar esta importación.")
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
        return HttpResponseForbidden("No tiene permiso para confirmar esta importación.")
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


@login_required
def calcular_mesas_eleccion(request, eleccion_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para calcular las mesas de esta elecciÃ³n.")
    if eleccion.estado not in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA):
        messages.error(request, "Solo se pueden calcular o recalcular mesas antes de abrir la elecciÃ³n.")
        return redirect("preparar-eleccion", eleccion_id=eleccion_id)
    try:
        resultado = calcular_mesas_automaticas_eleccion(eleccion, usuario=request.user, request=request)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Se calcularon las mesas de {len(resultado['claustros'])} claustros: "
            f"{resultado['mesas']} mesas para {resultado['electores']} electores.",
        )
    return redirect("preparar-eleccion", eleccion_id=eleccion_id)


@login_required
def configurar_sedes_claustro(request, eleccion_id, claustro_id):
    claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para configurar las sedes del padrón.")
    configuracion, _ = ConfiguracionSedesClaustro.objects.get_or_create(eleccion_claustro=claustro)

    if request.method == "POST" and request.POST.get("accion") == "calcular":
        resultado = calcular_asignaciones_sede_claustro(claustro)
        try:
            resultado_mesas = calcular_mesas_automaticas_eleccion(
                claustro.eleccion,
                usuario=request.user,
                request=request,
            )
        except ValueError as error:
            messages.warning(
                request,
                f"Sedes calculadas: {resultado['asignadas']} asignadas y {resultado['pendientes']} pendientes. "
                f"Las mesas anteriores se conservaron: {error}",
            )
        else:
            messages.success(
                request,
                f"Sedes calculadas: {resultado['asignadas']} asignadas y {resultado['pendientes']} pendientes. "
                f"Mesas recalculadas para toda la elección: {resultado_mesas['mesas']} mesas y "
                f"{resultado_mesas['electores']} electores.",
            )
        return redirect("configurar-sedes-claustro", eleccion_id=eleccion_id, claustro_id=claustro_id)

    if request.method == "POST" and request.POST.get("accion") == "eliminar-regla":
        regla = get_object_or_404(ReglaSedeClaustro, pk=request.POST.get("regla_id"), configuracion=configuracion)
        regla.delete()
        invalidar_asignaciones_sede_claustro(claustro)
        messages.success(request, "La regla se eliminó y el cálculo anterior quedó invalidado.")
        return redirect("configurar-sedes-claustro", eleccion_id=eleccion_id, claustro_id=claustro_id)

    accion_regla = request.POST.get("accion") if request.method == "POST" else None
    if accion_regla in ("mover-regla-subir", "mover-regla-bajar"):
        direccion = accion_regla.removeprefix("mover-regla-")
        regla = get_object_or_404(
            ReglaSedeClaustro,
            pk=request.POST.get("regla_id"),
            configuracion=configuracion,
        )
        if direccion == "subir":
            vecina = configuracion.reglas.filter(orden__lt=regla.orden).order_by("-orden", "-id").first()
        elif direccion == "bajar":
            vecina = configuracion.reglas.filter(orden__gt=regla.orden).order_by("orden", "id").first()
        else:
            vecina = None

        if vecina:
            ordenes_usados = set(configuracion.reglas.values_list("orden", flat=True))
            orden_temporal = next((orden for orden in range(1, 32768) if orden not in ordenes_usados), None)
            if orden_temporal is None:
                messages.error(request, "No se pudo cambiar el orden de las reglas.")
            else:
                with transaction.atomic():
                    orden_original = regla.orden
                    orden_vecina = vecina.orden
                    regla.orden = orden_temporal
                    regla.save(update_fields=("orden",))
                    vecina.orden = orden_original
                    vecina.save(update_fields=("orden",))
                    regla.orden = orden_vecina
                    regla.save(update_fields=("orden",))
                invalidar_asignaciones_sede_claustro(claustro)
                messages.success(request, "El orden de las reglas se actualizó y el cálculo anterior quedó invalidado.")
        else:
            messages.info(request, "La regla ya está en ese extremo del orden.")
        return redirect("configurar-sedes-claustro", eleccion_id=eleccion_id, claustro_id=claustro_id)

    formulario = FormularioReglaSedeClaustro(
        request.POST or None,
        eleccion_claustro=claustro,
        configuracion=configuracion,
        initial={
            "orden": (configuracion.reglas.order_by("-orden").values_list("orden", flat=True).first() or 0) + 1,
            "aplicar_a_todos": True,
        },
    )
    if request.method == "POST" and formulario.is_valid():
        regla = formulario.save(commit=False)
        regla.save()
        formulario.save_m2m()
        regla.full_clean()
        invalidar_asignaciones_sede_claustro(claustro)
        messages.success(request, "La regla se guardó. El cálculo anterior quedó invalidado.")
        return redirect("configurar-sedes-claustro", eleccion_id=eleccion_id, claustro_id=claustro_id)

    alcances = list(alcances_con_sedes_multiples(claustro).prefetch_related("sedes_habilitadas__sede"))
    asignaciones = AsignacionSedePadron.objects.filter(
        registro_padron__eleccion=claustro.eleccion,
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
        registro_padron__activo=True,
    ).select_related(
        "registro_padron__elector",
        "registro_padron__eleccion_claustro_departamento__departamento",
        "sede",
        "regla_aplicada",
    )
    cantidad_asignadas = asignaciones.filter(estado=AsignacionSedePadron.Estado.ASIGNADA).count()
    cantidad_pendientes = asignaciones.filter(estado=AsignacionSedePadron.Estado.PENDIENTE).count()
    cantidad_total = asignaciones.count()
    estado_filtro = request.GET.get("estado", "")
    estados_validos = {estado for estado, _etiqueta in AsignacionSedePadron.Estado.choices}
    if estado_filtro in estados_validos:
        asignaciones = asignaciones.filter(estado=estado_filtro)
    else:
        estado_filtro = ""
    asignaciones_paginadas = Paginator(asignaciones, 25).get_page(request.GET.get("pagina"))
    rango_paginas = [
        {
            "numero": numero,
            "actual": numero == asignaciones_paginadas.number,
            "elipsis": numero == asignaciones_paginadas.paginator.ELLIPSIS,
        }
        for numero in asignaciones_paginadas.paginator.get_elided_page_range(asignaciones_paginadas.number)
    ]
    return render(request, "padron/configurar_sedes_claustro.html", {
        "eleccion": claustro.eleccion,
        "claustro": claustro,
        "formulario": formulario,
        "reglas": configuracion.reglas.prefetch_related("alcances_especificos").all(),
        "alcances": alcances,
        "asignaciones": asignaciones_paginadas,
        "cantidad_asignadas": cantidad_asignadas,
        "cantidad_pendientes": cantidad_pendientes,
        "cantidad_total": cantidad_total,
        "estado_filtro": estado_filtro,
        "rango_paginas": rango_paginas,
    })
