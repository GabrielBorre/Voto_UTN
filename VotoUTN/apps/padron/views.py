import csv
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.forms import FormularioPrepararClaustro
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.mesas.models import Mesa
from apps.padron.models import (
    AsignacionSedePadron,
    ConfiguracionSedesClaustro,
    ImportacionPadron,
    SolicitudCambioSede,
    ReglaSedeClaustro,
)
from apps.padron.forms import FormularioArchivoPadron, FormularioReglaSedeClaustro, FormularioSolicitudCambioSede
from apps.padron.services_pdf import generar_padron_claustro_pdf, nombre_archivo_padron_claustro_pdf
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
    resolver_solicitud_cambio_sede,
    resolver_solicitudes_pendientes,
    registrar_errores,
    solicitudes_cambio_sede_habilitadas,
    estimar_mesas_adicionales_por_sede,
    validar_csv_padron,
)
from apps.usuarios.permisos import puede_administrar_elecciones, puede_importar_padron, puede_configurar_eleccion
from apps.padron.models import RegistroPadron
from apps.padron.services import calcular_mesas_automaticas_eleccion, claustro_tiene_emision_vigente
from apps.padron.services import eleccion_tiene_padron_emitido
from apps.notificaciones.services import (
    crear_notificacion_resultado_cambio_sede,
    enviar_notificacion,
)
from apps.usuarios.services import elector_de_identidad


@login_required
def descargar_plantilla_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion, solo_consulta=True):
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
def exportar_padron_claustro(request, eleccion_id, claustro_id, formato):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion, solo_consulta=True):
        return HttpResponseForbidden("No tiene permiso para exportar el padrón.")
    if formato not in {"csv", "pdf"}:
        raise Http404()
    registros = RegistroPadron.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related(
        "elector", "sede", "eleccion_claustro_departamento__departamento",
        "asignacion_mesa__mesa",
    ).order_by("elector__dni", "id")
    encabezados = ("DNI", "Tipo documento", "Legajo", "Nombre", "Correo", "Claustro", "Departamento", "Sede", "Mesa")
    filas = (
        (
            registro.elector.dni,
            registro.elector.tipo_documento,
            registro.elector.legajo,
            registro.elector.nombre_completo,
            registro.elector.correo_electronico,
            str(eleccion_claustro.claustro),
            str(registro.eleccion_claustro_departamento.departamento),
            str(registro.sede or ""),
            str(getattr(getattr(registro, "asignacion_mesa", None), "mesa", "") or ""),
        )
        for registro in registros
    )
    nombre = f"padron_{eleccion_claustro.claustro.nombre}_{eleccion_id}"
    if formato == "pdf":
        respuesta = HttpResponse(
            generar_padron_claustro_pdf(eleccion_claustro, registros),
            content_type="application/pdf",
        )
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo_padron_claustro_pdf(eleccion_claustro)}"'
        return respuesta
    if formato == "csv":
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.csv"'
        respuesta.write("\ufeff")
        escritor = csv.writer(respuesta)
        escritor.writerow(encabezados)
        escritor.writerows(filas)
        return respuesta
    raise Http404()


@login_required
def previsualizar_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    if not puede_importar_padron(request.user, eleccion_claustro.eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para importar el padrón.")
    if not puede_configurar_eleccion(request.user, eleccion_claustro.eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No se puede modificar el padrón de una elección cerrada.")
    configura_padron = request.method == "POST" and "guardar-configuracion" in request.POST
    carga_archivo = request.method == "POST" and not configura_padron
    autoguardado = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.POST.get("autoguardado") == "1"
    puede_configurar = puede_configurar_eleccion(request.user, eleccion_claustro.eleccion)
    puede_cargar = puede_configurar and eleccion_claustro.eleccion.estado == Eleccion.Estado.BORRADOR

    if configura_padron and not puede_configurar:
        return HttpResponseForbidden("No tiene permiso para configurar este padrón.")
    if carga_archivo and not puede_cargar:
        return HttpResponseForbidden("Solo se puede importar padrón en estado En preparación.")

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
            except ValueError:
                mensaje_error_mesas = "Configuración guardada; las mesas no se pudieron recalcular."
                if autoguardado:
                    return JsonResponse(
                        {"mensaje": mensaje_error_mesas}
                    )
                messages.warning(request, mensaje_error_mesas)
                return redirect(
                    "previsualizar-padron",
                    eleccion_id=eleccion_id,
                    claustro_id=claustro_id,
                )
            else:
                mensaje_mesas = (
                    f"Mesas recalculadas automáticamente: {resultado_mesas['mesas']} mesas "
                    f"para {resultado_mesas['electores']} electores."
                )
        if autoguardado:
            return JsonResponse({"mensaje": mensaje_mesas or "Configuración guardada automáticamente."})
        if mensaje_mesas:
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
            cantidad_validas=resultado.cantidad_validas,
            cantidad_existentes=resultado.cantidad_existentes,
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
    if not puede_configurar_eleccion(request.user, claustro.eleccion, solo_consulta=request.method in ("GET", "HEAD")):
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
            f"Se eliminaron {resumen['cantidad_registros']} registros del padrón.",
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
    if not puede_importar_padron(request.user, importacion.eleccion, solo_consulta=True):
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
    if not puede_configurar_eleccion(request.user, importacion.eleccion):
        return HttpResponseForbidden("No se puede confirmar una importación para una elección cerrada.")
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
            f"Padrón confirmado: {cantidad} electores nuevos, "
            f"{cantidad_existente} electores ya existentes.",
        )
    return redirect("detalle-importacion-padron", eleccion_id=eleccion_id, importacion_id=importacion.id)


@login_required
def descargar_errores_importacion(request, eleccion_id, importacion_id):
    importacion = get_object_or_404(ImportacionPadron, pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion, solo_consulta=True):
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
    if not puede_importar_padron(request.user, eleccion, solo_consulta=True):
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
        messages.error(request, "Solo se pueden calcular o recalcular mesas antes de iniciar la elección.")
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
    if not puede_configurar_eleccion(request.user, claustro.eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para configurar las sedes del padrón.")
    configuracion = ConfiguracionSedesClaustro.objects.filter(eleccion_claustro=claustro).first()
    if configuracion is None:
        if not puede_configurar_eleccion(request.user, claustro.eleccion):
            messages.info(request, "Este claustro no tiene reglas de sede configuradas.")
            return redirect("previsualizar-padron", eleccion_id=eleccion_id, claustro_id=claustro_id)
        configuracion = ConfiguracionSedesClaustro.objects.create(eleccion_claustro=claustro)

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


@login_required
def mis_solicitudes_cambio_sede(request):
    elector = elector_de_identidad(request.user)
    if elector is None:
        return HttpResponseForbidden("No existe un elector asociado a esta identidad.")
    registros = RegistroPadron.objects.filter(
        elector=elector,
        activo=True,
        eleccion__estado=Eleccion.Estado.PREPARADA,
    ).select_related("eleccion", "sede", "eleccion_claustro_departamento__eleccion_claustro__claustro")
    registro = registros.order_by("-eleccion__fecha_inicio", "-eleccion_id").first()
    formulario = None
    if registro is not None:
        formulario = FormularioSolicitudCambioSede(request.POST or None, registro_padron=registro)
        solicitud_existente = SolicitudCambioSede.objects.filter(registro_padron=registro).first()
        if request.method == "POST":
            if solicitud_existente is not None:
                messages.error(request, "Ya registraste una solicitud de cambio de sede para esta elección.")
                return redirect("mis-solicitudes-cambio-sede")
            if not solicitudes_cambio_sede_habilitadas(registro.eleccion):
                messages.error(request, "El período para solicitar cambio de sede no está habilitado.")
                return redirect("mis-solicitudes-cambio-sede")
            if formulario.is_valid():
                formulario.save()
                messages.success(request, "La solicitud fue enviada para revisión.")
                return redirect("mis-solicitudes-cambio-sede")
    else:
        solicitud_existente = None
    solicitudes = SolicitudCambioSede.objects.filter(
        registro_padron__elector=elector,
    ).select_related("registro_padron__eleccion", "sede_origen", "sede_destino", "resuelta_por")
    return render(
        request,
        "padron/mis_solicitudes_cambio_sede.html",
        {
            "registro": registro,
            "solicitudes": solicitudes,
            "formulario": formulario,
            "periodo_habilitado": bool(registro and solicitudes_cambio_sede_habilitadas(registro.eleccion)),
            "solicitud_existente": solicitud_existente,
        },
    )


@login_required
def gestionar_solicitudes_cambio_sede(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para revisar solicitudes de cambio de sede.")
    solo_lectura = (
        eleccion.estado not in (Eleccion.Estado.PREPARADA, Eleccion.Estado.ABIERTA)
        or eleccion_tiene_padron_emitido(eleccion)
    )
    if request.method == "POST":
        if solo_lectura:
            return HttpResponseForbidden("Los cambios de sede están en modo lectura.")
        accion = request.POST.get("accion")
        observacion = request.POST.get("observacion_resolucion", "")
        if accion in {"aprobar", "rechazar"}:
            solicitud = get_object_or_404(
                SolicitudCambioSede.objects.select_related("registro_padron__eleccion"),
                pk=request.POST.get("solicitud_id"),
                registro_padron__eleccion=eleccion,
            )
            try:
                solicitud = resolver_solicitud_cambio_sede(
                    solicitud,
                    SolicitudCambioSede.Estado.APROBADA if accion == "aprobar" else SolicitudCambioSede.Estado.RECHAZADA,
                    request.user,
                    observacion,
                )
            except ValueError as error:
                messages.error(request, str(error))
            else:
                envio = crear_notificacion_resultado_cambio_sede(solicitud)
                enviar_notificacion(envio)
                messages.success(request, "La solicitud fue resuelta y se notificó al elector.")
            return redirect("gestionar-solicitudes-cambio-sede", eleccion_id=eleccion.id)

        if accion in {
            "aprobar_todas",
            "aprobar_sin_agregar_mesas",
            "aprobar_con_maximo_mesas",
            "aprobar_seleccionadas",
            "rechazar_todas",
        }:
            maximo_mesas_nuevas = None
            if accion == "aprobar_con_maximo_mesas":
                try:
                    maximo_mesas_nuevas = int(request.POST.get("maximo_mesas_nuevas", ""))
                    if maximo_mesas_nuevas < 0:
                        raise ValueError
                except ValueError:
                    messages.error(request, "Ingresá un máximo de mesas nuevas entero y mayor o igual a cero.")
                    return redirect("gestionar-solicitudes-cambio-sede", eleccion_id=eleccion.id)
            try:
                seleccion_ids = None
                if accion == "aprobar_seleccionadas":
                    seleccion = request.POST.getlist("solicitudes_ids")
                    if any(not valor.isdecimal() for valor in seleccion):
                        raise ValueError("La selección de solicitudes es inválida.")
                    seleccion_ids = [int(valor) for valor in seleccion]
                resultado = resolver_solicitudes_pendientes(
                    eleccion,
                    usuario=request.user,
                    accion="aprobar_todas" if accion == "aprobar_seleccionadas" else accion,
                    observacion_resolucion=observacion,
                    maximo_mesas_nuevas=maximo_mesas_nuevas,
                    solicitudes_ids=seleccion_ids,
                )
            except ValueError as error:
                messages.error(request, str(error))
            else:
                for solicitud in SolicitudCambioSede.objects.filter(pk__in=resultado["resueltas_ids"]):
                    envio = crear_notificacion_resultado_cambio_sede(solicitud)
                    enviar_notificacion(envio)
                messages.success(
                    request,
                    f"Solicitudes resueltas. Aprobadas: {resultado['aprobadas']}. "
                    f"Rechazadas: {resultado['rechazadas']}. Pendientes: {resultado['pendientes']}.",
                )
            return redirect("gestionar-solicitudes-cambio-sede", eleccion_id=eleccion.id)

    solicitudes = SolicitudCambioSede.objects.filter(
        registro_padron__eleccion=eleccion,
    ).select_related(
        "registro_padron__elector",
        "registro_padron__eleccion_claustro_departamento__eleccion_claustro__claustro",
        "sede_origen",
        "sede_destino",
    )
    pendientes = solicitudes.filter(estado=SolicitudCambioSede.Estado.PENDIENTE)
    if request.GET.get("accion") == "estimar_seleccion":
        ids = request.GET.getlist("solicitudes_ids")
        if any(not valor.isdecimal() for valor in ids):
            return JsonResponse({"error": "La selección de solicitudes es inválida."}, status=400)
        seleccionadas = pendientes.filter(pk__in=[int(valor) for valor in ids])
        if seleccionadas.count() != len(set(ids)):
            return JsonResponse({"error": "La selección contiene solicitudes no disponibles."}, status=400)
        impacto_seleccion = estimar_mesas_adicionales_por_sede(eleccion, seleccionadas)
        return JsonResponse({
            "mesas_por_sede": impacto_seleccion,
            "total": sum(impacto_seleccion.values()),
            "seleccionadas": seleccionadas.count(),
        })
    impacto = estimar_mesas_adicionales_por_sede(eleccion, pendientes)
    sedes = list(eleccion.elecciones_sede.select_related("sede").order_by("sede__nombre"))
    mesas_actuales_por_sede = dict(
        Mesa.objects.filter(eleccion=eleccion, sede_id__in=[item.sede_id for item in sedes])
        .values("sede_id")
        .annotate(cantidad=Count("id"))
        .values_list("sede_id", "cantidad")
    )
    resumen_mesas_por_sede = [
        {
            "sede_id": item.sede_id,
            "sede_nombre": item.sede.nombre,
            "mesas_actuales": mesas_actuales_por_sede.get(item.sede_id, 0),
            "mesas_adicionales_estimadas": impacto.get(item.sede_id, 0),
        }
        for item in sedes
    ]
    return render(
        request,
        "padron/gestion_solicitudes_cambio_sede.html",
        {
            "eleccion": eleccion,
            "solicitudes": solicitudes,
            "pendientes": pendientes.count(),
            "resumen_mesas_por_sede": resumen_mesas_por_sede,
            "mesas_nuevas_si_aceptar_todas": sum(impacto.values()),
            "solo_lectura": solo_lectura,
        },
    )
