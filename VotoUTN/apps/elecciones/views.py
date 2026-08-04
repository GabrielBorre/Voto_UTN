import csv
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    FormularioAlcanceSedes,
    FormularioArchivoAutoridades,
    FormularioArchivoPadron,
    FormularioAsignacionAutoridad,
    FormularioClaustro,
    FormularioDepartamento,
    FormularioEleccion,
    FormularioEditarEleccion,
    FormularioFechaAdministrativa,
    FormularioGenerarMesas,
    FormularioJustificativo,
    FormularioPrepararClaustro,
    FormularioPreferenciaAutoridad,
    FormularioResolucionJustificativo,
    FormularioSede,
    FormularioTurno,
    FormularioTipoJustificativo,
    FormularioPlantillaNotificacion,
    FormularioEnviarNotificacion,
    preparar_formulario_parametro,
)
from .models import AsignacionAutoridad, Claustro, Departamento, Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EnvioNotificacion, FechaAdministrativa, ImportacionPadron, JustificativoAusencia, PlantillaNotificacion, PreferenciaAutoridad, Sede, TipoJustificativo, Turno
from .servicios.autoridades import asignar_autoridad, importar_autoridades, responder_asignacion
from .servicios.importacion_padron import CABECERAS_PADRON, confirmar_importacion, registrar_errores, validar_csv_padron
from .servicios.notificaciones import crear_envios
from apps.usuarios.permisos import elecciones_con_participacion
from apps.usuarios.permisos import puede_administrar_elecciones, puede_administrar_parametros, puede_importar_padron, puede_revisar_justificativo
from apps.usuarios.models import AsignacionRol


PARAMETROS = {
    "sedes": {"modelo": Sede, "formulario": FormularioSede, "titulo": "Sedes", "estado": "activa", "codigo": False},
    "claustros": {"modelo": Claustro, "formulario": FormularioClaustro, "titulo": "Claustros", "estado": "activo", "codigo": False},
    "departamentos": {"modelo": Departamento, "formulario": FormularioDepartamento, "titulo": "Departamentos", "estado": "activo", "codigo": True},
    "turnos": {"modelo": Turno, "formulario": FormularioTurno, "titulo": "Turnos", "estado": "activo", "codigo": False},
    "fechas-administrativas": {"modelo": FechaAdministrativa, "formulario": FormularioFechaAdministrativa, "titulo": "Fechas administrativas", "estado": "activa", "codigo": False, "es_fecha": True},
    "tipos-justificativo": {"modelo": TipoJustificativo, "formulario": FormularioTipoJustificativo, "titulo": "Tipos de justificativo", "estado": "activo", "codigo": False},
}


def contexto_formulario_eleccion(formulario, incluir_parametros=False):
    contexto = {
        "campos_generales": [formulario[nombre] for nombre in ("nombre", "fecha_inicio", "fecha_fin")],
        "campos_fechas_administrativas": [
            {
                "definicion": definicion,
                "seleccionada": formulario[f"fecha_{definicion.id}_seleccionada"],
                "fecha": formulario[f"fecha_{definicion.id}_valor"],
            }
            for definicion in getattr(formulario, "definiciones_fechas", [])
        ],
    }
    if incluir_parametros:
        contexto["campos_parametros"] = [formulario[nombre] for nombre in ("sedes", "claustros", "turnos")]
    return contexto


def obtener_parametro(tipo):
    try:
        return PARAMETROS[tipo]
    except KeyError as error:
        raise Http404("Tipo de parametro inexistente.") from error

@login_required
def listar_elecciones(request):
    return render(request, "elecciones/list.html", {"elecciones": elecciones_con_participacion(request.user)})


@login_required
def gestionar_parametros(request):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    parametros = [
        {"tipo": tipo, "titulo": configuracion["titulo"], "cantidad": configuracion["modelo"].objects.count()}
        for tipo, configuracion in PARAMETROS.items()
    ]
    return render(request, "elecciones/parametros.html", {"parametros": parametros})


@login_required
def listar_parametros(request, tipo):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    configuracion = obtener_parametro(tipo)
    consulta = request.GET.get("q", "").strip()
    objetos = configuracion["modelo"].objects.all()
    if consulta:
        filtro = Q(nombre__icontains=consulta)
        if configuracion["codigo"]:
            filtro |= Q(codigo__icontains=consulta)
        objetos = objetos.filter(filtro)
    return render(
        request,
        "elecciones/parametro_lista.html",
        {"tipo": tipo, "titulo": configuracion["titulo"], "objetos": objetos, "consulta": consulta, "campo_estado": configuracion["estado"], "tiene_codigo": configuracion["codigo"], "es_fecha": configuracion.get("es_fecha", False)},
    )


@login_required
def editar_parametro(request, tipo, objeto_id=None):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    configuracion = obtener_parametro(tipo)
    objeto = get_object_or_404(configuracion["modelo"], pk=objeto_id) if objeto_id else None
    formulario = preparar_formulario_parametro(configuracion["formulario"](request.POST or None, instance=objeto))
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, f"{configuracion['titulo'][:-1]} guardado correctamente.")
        return redirect("listar-parametros", tipo=tipo)
    return render(
        request,
        "elecciones/parametro_formulario.html",
        {"tipo": tipo, "titulo": configuracion["titulo"], "formulario": formulario, "objeto": objeto},
    )


@login_required
def cambiar_estado_parametro(request, tipo, objeto_id):
    if request.method != "POST":
        raise Http404()
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    configuracion = obtener_parametro(tipo)
    objeto = get_object_or_404(configuracion["modelo"], pk=objeto_id)
    campo_estado = configuracion["estado"]
    setattr(objeto, campo_estado, not getattr(objeto, campo_estado))
    objeto.save(update_fields=(campo_estado,))
    messages.success(request, "El estado fue actualizado.")
    return redirect("listar-parametros", tipo=tipo)


@login_required
def gestionar_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar elecciones.")
    return render(request, "elecciones/gestion_lista.html", {"elecciones": Eleccion.objects.all()})


@login_required
def historial_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para consultar el historial.")
    return render(request, "elecciones/historial_elecciones.html", {"elecciones": Eleccion.objects.all()})


@login_required
def configurar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para configurar esta eleccion.")
    return render(
        request,
        "elecciones/configurar_eleccion.html",
        {
            "eleccion": eleccion,
            "cantidad_padrones": eleccion.registros_padron.count(),
            "cantidad_mesas": eleccion.mesas.count(),
            "cantidad_autoridades": AsignacionAutoridad.objects.filter(mesa__eleccion=eleccion).count(),
        },
    )


@login_required
def gestionar_autoridades(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar autoridades.")
    formulario_manual = FormularioAsignacionAutoridad(request.POST or None, eleccion=eleccion, prefix="manual")
    formulario_csv = FormularioArchivoAutoridades(request.POST or None, request.FILES or None, prefix="csv")
    if request.method == "POST" and "manual-candidatura" in request.POST and formulario_manual.is_valid():
        try:
            _, creada = asignar_autoridad(formulario_manual.cleaned_data["candidatura"].registro_padron, formulario_manual.cleaned_data["mesa"], request.user)
        except ValidationError as error:
            formulario_manual.add_error(None, error.messages[0])
        else:
            messages.success(request, "Autoridad asignada." if creada else "El elector ya era autoridad de esta mesa.")
            return redirect("gestionar-autoridades", eleccion_id=eleccion.id)
    if request.method == "POST" and "csv-archivo" in request.FILES and formulario_csv.is_valid():
        cantidad, errores = importar_autoridades(formulario_csv.cleaned_data["archivo"].read(), eleccion, request.user)
        if errores:
            formulario_csv.add_error("archivo", "El CSV contiene errores: " + " ".join(f"Fila {fila}: {mensaje}" for fila, mensaje in errores[:3]))
        else:
            messages.success(request, f"Se cargaron {cantidad} candidatos desde el CSV.")
            return redirect("gestionar-autoridades", eleccion_id=eleccion.id)
    autoridades = AsignacionAutoridad.objects.filter(mesa__eleccion=eleccion).select_related("registro_padron__elector", "mesa", "asignada_por")
    return render(request, "elecciones/gestion_autoridades.html", {"eleccion": eleccion, "formulario_manual": formulario_manual, "formulario_csv": formulario_csv, "autoridades": autoridades})


@login_required
def crear_eleccion(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para crear elecciones.")

    formulario = FormularioEleccion(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        eleccion = formulario.save()
        messages.success(request, "La eleccion fue creada y quedo configurada.")
        return redirect("preparar-eleccion", eleccion_id=eleccion.id)
    return render(request, "elecciones/formulario_eleccion.html", {"formulario": formulario, **contexto_formulario_eleccion(formulario, incluir_parametros=True)})


@login_required
def preparar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para preparar esta eleccion.")
    claustros = eleccion.elecciones_claustro.select_related("claustro").prefetch_related("departamentos__departamento", "sedes_habilitadas__sede")
    return render(request, "elecciones/preparar_eleccion.html", {"eleccion": eleccion, "claustros": claustros})


@login_required
def preparar_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para preparar este claustro.")
    formulario = FormularioPrepararClaustro(request.POST or None, instance=eleccion_claustro)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "La configuracion del claustro fue guardada.")
        return redirect("preparar-eleccion", eleccion_id=eleccion_id)
    return render(request, "elecciones/preparar_claustro.html", {"eleccion": eleccion_claustro.eleccion, "claustro": eleccion_claustro, "formulario": formulario})


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
        return HttpResponseForbidden("No tiene permiso para importar el padrón.")
    if eleccion_claustro.eleccion.estado not in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA):
        return HttpResponseForbidden("No se puede importar un padrón para una elección abierta o cerrada.")
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
    return render(request, "elecciones/cargar_padron.html", {"eleccion": eleccion_claustro.eleccion, "claustro": eleccion_claustro, "formulario": formulario})


@login_required
def detalle_importacion_padron(request, eleccion_id, importacion_id):
    importacion = get_object_or_404(ImportacionPadron.objects.select_related("eleccion_claustro__claustro", "usuario"), pk=importacion_id, eleccion_id=eleccion_id)
    if not puede_importar_padron(request.user, importacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar esta importación.")
    return render(request, "elecciones/detalle_importacion_padron.html", {"eleccion": importacion.eleccion, "importacion": importacion})


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
        messages.success(request, f"Padrón confirmado. Se incorporaron {cantidad} registros nuevos.")
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
    return render(request, "elecciones/historial_importaciones_padron.html", {"eleccion": eleccion, "importaciones": importaciones})


@login_required
def mis_asignaciones_autoridad(request):
    perfil = getattr(request.user, "perfil_electoral", None)
    asignaciones = AsignacionAutoridad.objects.select_related("mesa__sede", "mesa__turno", "registro_padron__eleccion", "registro_padron__elector")
    if request.user.is_superuser:
        return render(request, "elecciones/mis_asignaciones_autoridad.html", {"asignaciones": asignaciones, "vista_administrativa": True})
    if perfil and perfil.elector_id:
        asignaciones = asignaciones.filter(registro_padron__elector=perfil.elector)
    elif not request.user.asignaciones_rol.filter(rol="autoridad_mesa", activo=True).exists():
        return HttpResponseForbidden("No tiene permiso de autoridad de mesa.")
    else:
        asignaciones = asignaciones.none()
    return render(request, "elecciones/mis_asignaciones_autoridad.html", {"asignaciones": asignaciones})


@login_required
def responder_autoridad(request, asignacion_id):
    if request.method != "POST":
        raise Http404()
    perfil = getattr(request.user, "perfil_electoral", None)
    asignacion = get_object_or_404(AsignacionAutoridad, pk=asignacion_id, registro_padron__elector=getattr(perfil, "elector", None))
    responder_asignacion(asignacion, request.POST.get("respuesta") == "aceptar")
    messages.success(request, "La respuesta fue registrada.")
    return redirect("mis-asignaciones-autoridad")


@login_required
def preferencia_autoridad(request, asignacion_id):
    perfil = getattr(request.user, "perfil_electoral", None)
    asignacion = get_object_or_404(AsignacionAutoridad.objects.select_related("registro_padron__eleccion"), pk=asignacion_id, registro_padron__elector=getattr(perfil, "elector", None))
    preferencia, _ = PreferenciaAutoridad.objects.get_or_create(registro_padron=asignacion.registro_padron)
    formulario = FormularioPreferenciaAutoridad(request.POST or None, instance=preferencia, eleccion=asignacion.registro_padron.eleccion, registro_padron=asignacion.registro_padron)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "La preferencia fue actualizada.")
        return redirect("mis-asignaciones-autoridad")
    return render(request, "elecciones/preferencia_autoridad.html", {"asignacion": asignacion, "formulario": formulario})


@login_required
def mis_justificativos(request):
    perfil = getattr(request.user, "perfil_electoral", None)
    elector = perfil.elector if perfil and perfil.elector_id else None
    formulario = FormularioJustificativo(request.POST or None, request.FILES or None, elector=elector)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "El justificativo fue presentado para revision.")
        return redirect("mis-justificativos")
    justificativos = JustificativoAusencia.objects.select_related("registro_padron__eleccion", "tipo")
    if elector is not None:
        justificativos = justificativos.filter(registro_padron__elector=elector)
    return render(request, "elecciones/mis_justificativos.html", {"formulario": formulario, "justificativos": justificativos})


@login_required
def gestionar_justificativos(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_revisar_justificativo(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para revisar justificativos.")
    justificativos = JustificativoAusencia.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector", "tipo", "resuelta_por")
    return render(request, "elecciones/gestion_justificativos.html", {"eleccion": eleccion, "justificativos": justificativos})


@login_required
def bandeja_justificativos(request):
    if request.user.is_superuser or AsignacionRol.objects.filter(usuario=request.user, activo=True, rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        justificativos = JustificativoAusencia.objects.all()
    else:
        elecciones = AsignacionRol.objects.filter(
            usuario=request.user,
            activo=True,
            rol__in=(AsignacionRol.Rol.ADMINISTRADOR_JUNTA, AsignacionRol.Rol.ADMINISTRATIVO_JUNTA),
        ).exclude(eleccion__isnull=True).values_list("eleccion_id", flat=True)
        justificativos = JustificativoAusencia.objects.filter(registro_padron__eleccion_id__in=elecciones)
    if not justificativos.exists():
        tiene_rol = AsignacionRol.objects.filter(usuario=request.user, activo=True, rol__in=(AsignacionRol.Rol.ADMINISTRADOR_JUNTA, AsignacionRol.Rol.ADMINISTRATIVO_JUNTA)).exists()
        if not (request.user.is_superuser or tiene_rol):
            return HttpResponseForbidden("No tiene permiso para revisar justificativos.")
    justificativos = justificativos.select_related("registro_padron__eleccion", "registro_padron__elector", "tipo")
    return render(request, "elecciones/bandeja_justificativos.html", {"justificativos": justificativos})


@login_required
def resolver_justificativo(request, justificativo_id):
    justificativo = get_object_or_404(JustificativoAusencia.objects.select_related("registro_padron__eleccion"), pk=justificativo_id)
    if not puede_revisar_justificativo(request.user, justificativo.registro_padron.eleccion):
        return HttpResponseForbidden("No tiene permiso para resolver este justificativo.")
    formulario = FormularioResolucionJustificativo(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        justificativo.estado = formulario.cleaned_data["estado"]
        justificativo.observacion_resolucion = formulario.cleaned_data["observacion_resolucion"]
        justificativo.resuelta_por = request.user
        justificativo.resuelta_en = timezone.now()
        justificativo.save(update_fields=("estado", "observacion_resolucion", "resuelta_por", "resuelta_en"))
        messages.success(request, "El justificativo fue resuelto.")
        return redirect("gestionar-justificativos", eleccion_id=justificativo.registro_padron.eleccion_id)
    return render(request, "elecciones/resolver_justificativo.html", {"justificativo": justificativo, "formulario": formulario})


@login_required
def gestionar_notificaciones(request):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar notificaciones.")
    formulario_plantilla = FormularioPlantillaNotificacion(request.POST or None, prefix="plantilla")
    formulario_envio = FormularioEnviarNotificacion(request.POST or None, prefix="envio")
    if request.method == "POST" and "plantilla-nombre" in request.POST and formulario_plantilla.is_valid():
        formulario_plantilla.save()
        messages.success(request, "La plantilla fue guardada.")
        return redirect("gestionar-notificaciones")
    if request.method == "POST" and "envio-plantilla" in request.POST and formulario_envio.is_valid():
        cantidad = crear_envios(formulario_envio.cleaned_data["plantilla"], formulario_envio.cleaned_data["eleccion"])
        messages.success(request, f"Se generaron {cantidad} notificaciones pendientes.")
        return redirect("gestionar-notificaciones")
    return render(request, "elecciones/gestion_notificaciones.html", {"formulario_plantilla": formulario_plantilla, "formulario_envio": formulario_envio, "plantillas": PlantillaNotificacion.objects.all(), "envios": EnvioNotificacion.objects.select_related("destinatario", "eleccion")[:20]})


def valor_csv(valor):
    texto = "" if valor is None else str(valor)
    return f"'{texto}" if texto.startswith(("=", "+", "-", "@")) else texto


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
        return HttpResponseForbidden("No tiene permiso para exportar información.")
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{tipo}_{eleccion.id}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    if tipo == "padron":
        escritor.writerow(("dni", "legajo", "nombre", "correo", "claustro", "departamento", "sede", "mesa"))
        for registro in eleccion.registros_padron.select_related("elector", "sede", "eleccion_claustro_departamento__departamento", "eleccion_claustro_departamento__eleccion_claustro__claustro", "asignacion_mesa__mesa"):
            escritor.writerow([valor_csv(valor) for valor in (registro.elector.dni, registro.elector.legajo, registro.elector.nombre, registro.elector.correo_electronico, registro.eleccion_claustro_departamento.eleccion_claustro.claustro, registro.eleccion_claustro_departamento.departamento, registro.sede, getattr(getattr(registro, "asignacion_mesa", None), "mesa", None))])
    elif tipo == "mesas":
        escritor.writerow(("numero", "claustro", "departamento", "sede", "turno", "origen"))
        for mesa in eleccion.mesas.select_related("sede", "turno", "eleccion_claustro_departamento__departamento", "eleccion_claustro_departamento__eleccion_claustro__claustro"):
            escritor.writerow((mesa.numero, mesa.eleccion_claustro_departamento.eleccion_claustro.claustro, mesa.eleccion_claustro_departamento.departamento, mesa.sede, mesa.turno, "padron" if mesa.generada_automaticamente else "manual"))
    elif tipo == "autoridades":
        escritor.writerow(("nombre", "legajo", "mesa", "estado", "asignada_en"))
        for item in AsignacionAutoridad.objects.filter(mesa__eleccion=eleccion).select_related("registro_padron__elector", "mesa"):
            escritor.writerow((valor_csv(item.registro_padron.elector.nombre), valor_csv(item.registro_padron.elector.legajo), item.mesa.numero, item.estado, item.asignada_en.isoformat()))
    elif tipo == "participacion":
        from apps.asistencia.models import RegistroParticipacion
        escritor.writerow(("elector", "legajo", "mesa", "registrada_en", "metodo"))
        for item in RegistroParticipacion.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector", "mesa"):
            escritor.writerow((valor_csv(item.registro_padron.elector.nombre), valor_csv(item.registro_padron.elector.legajo), item.mesa.numero, item.registrada_en.isoformat(), item.metodo))
    elif tipo == "justificativos":
        escritor.writerow(("elector", "motivo", "estado", "presentada_en", "resuelta_en"))
        for item in JustificativoAusencia.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector", "tipo"):
            escritor.writerow([valor_csv(valor) for valor in (item.registro_padron.elector.nombre, item.tipo, item.estado, item.presentada_en.isoformat(), item.resuelta_en.isoformat() if item.resuelta_en else "")])
    elif tipo == "errores-importacion":
        escritor.writerow(("archivo", "fila", "campo", "mensaje"))
        for error in eleccion.importaciones_padron.prefetch_related("errores").all():
            for detalle in error.errores.all():
                escritor.writerow([valor_csv(valor) for valor in (error.nombre_archivo, detalle.fila, detalle.campo, detalle.mensaje)])
    else:
        raise Http404()
    return respuesta


@login_required
def mis_notificaciones(request):
    notificaciones = request.user.notificaciones.all()
    return render(request, "elecciones/mis_notificaciones.html", {"notificaciones": notificaciones})


@login_required
def leer_notificacion(request, notificacion_id):
    notificacion = get_object_or_404(EnvioNotificacion, pk=notificacion_id, destinatario=request.user)
    if notificacion.leida_en is None:
        notificacion.leida_en = timezone.now()
        notificacion.save(update_fields=("leida_en",))
    return render(request, "elecciones/detalle_notificacion.html", {"notificacion": notificacion})


@login_required
def editar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para editar esta eleccion.")
    if eleccion.estado in (Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
        return HttpResponseForbidden("No se puede editar una eleccion abierta o cerrada.")
    formulario = FormularioEditarEleccion(request.POST or None, instance=eleccion)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Los datos de la eleccion fueron actualizados.")
        return redirect("gestionar-elecciones")
    return render(request, "elecciones/editar_eleccion.html", {"eleccion": eleccion, "formulario": formulario, **contexto_formulario_eleccion(formulario)})


@login_required
def cambiar_estado_eleccion(request, eleccion_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para cambiar esta eleccion.")
    nuevo_estado = request.POST.get("estado")
    try:
        eleccion.cambiar_estado(nuevo_estado)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"La eleccion quedo {eleccion.get_estado_display().lower()}.")
    return redirect("gestionar-elecciones")


@login_required
def gestionar_alcances(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")
    return render(
        request,
        "elecciones/alcances.html",
        {
            "eleccion": eleccion,
            "claustros": eleccion.elecciones_claustro.select_related("claustro").prefetch_related("departamentos__departamento"),
        },
    )


@login_required
def editar_alcance_sedes(request, eleccion_id, tipo, objeto_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")
    if eleccion.estado in (Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
        return HttpResponseForbidden("No se pueden modificar alcances en una eleccion abierta o cerrada.")
    if tipo == "claustro":
        objeto = get_object_or_404(EleccionClaustro, pk=objeto_id, eleccion=eleccion)
        titulo = f"Sedes de {objeto.claustro}"
    elif tipo == "departamento":
        objeto = get_object_or_404(EleccionClaustroDepartamento, pk=objeto_id, eleccion_claustro__eleccion=eleccion)
        titulo = f"Sedes de {objeto.departamento}"
    else:
        raise Http404()
    formulario = FormularioAlcanceSedes(request.POST or None, eleccion=eleccion, objeto=objeto, tipo=tipo)
    if request.method == "POST" and formulario.is_valid():
        formulario.guardar()
        messages.success(request, "Las sedes habilitadas fueron actualizadas.")
        return redirect("gestionar-alcances", eleccion_id=eleccion.id)
    return render(request, "elecciones/editar_alcance.html", {"eleccion": eleccion, "titulo": titulo, "formulario": formulario})


@login_required
def gestionar_mesas(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")

    return render(
        request,
        "elecciones/gestion_mesas.html",
        {"eleccion": eleccion, "mesas": eleccion.mesas.select_related("sede", "turno", "eleccion_claustro_departamento__eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento")},
    )
