import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.autoridades.forms import (
    FormularioArchivoAutoridades,
    FormularioAsignacionAutoridad,
    FormularioPreferenciaAutoridad,
    FormularioTurnosAutoridades,
)
from apps.autoridades.services import PLANTILLA_AUTORIDADES_EJEMPLO, PLANTILLA_AUTORIDADES_HEADERS, asignar_autoridad, importar_autoridades, responder_asignacion
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.mesas.models import Mesa
from apps.usuarios.permisos import puede_administrar_elecciones
from apps.usuarios.services import elector_de_identidad


@login_required
def descargar_plantilla_autoridades(request, eleccion_id, claustro_id=None):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar la plantilla.")
    eleccion_claustro = None
    if claustro_id is not None:
        eleccion_claustro = get_object_or_404(
            EleccionClaustro.objects.select_related("claustro"),
            pk=claustro_id,
            eleccion=eleccion,
        )
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    sufijo = f"_{eleccion_claustro.claustro.nombre}" if eleccion_claustro else ""
    respuesta["Content-Disposition"] = f'attachment; filename="plantilla_autoridades_{eleccion.id}{sufijo}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(PLANTILLA_AUTORIDADES_HEADERS)
    for fila in PLANTILLA_AUTORIDADES_EJEMPLO:
        escritor.writerow(fila)
    return respuesta


@login_required
def gestionar_autoridades(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar autoridades.")
    resumen_claustros = []
    for eleccion_claustro in eleccion.elecciones_claustro.select_related("claustro").order_by("claustro__nombre"):
        alcance = {
            "registro_padron__eleccion_claustro_departamento__eleccion_claustro": eleccion_claustro,
        }
        asignaciones = AsignacionAutoridad.objects.filter(**alcance)
        resumen_claustros.append(
            {
                "eleccion_claustro": eleccion_claustro,
                "turnos": eleccion_claustro.turnos_autoridad.count(),
                "candidatos": CandidaturaAutoridad.objects.filter(**alcance).count(),
                "mesas": Mesa.objects.filter(
                    eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                ).count(),
                "asignadas": asignaciones.count(),
                "pendientes": asignaciones.filter(estado=AsignacionAutoridad.Estado.PENDIENTE).count(),
            }
        )
    return render(
        request,
        "autoridades/gestion.html",
        {
            "eleccion": eleccion,
            "resumen_claustros": resumen_claustros,
        },
    )


@login_required
def gestionar_autoridades_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    eleccion = eleccion_claustro.eleccion
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar autoridades.")

    configura_turnos = request.method == "POST" and "guardar-turnos" in request.POST
    asigna_autoridad = request.method == "POST" and "asignar-autoridad" in request.POST
    carga_candidatos = request.method == "POST" and "cargar-candidatos" in request.POST
    formulario_turnos = FormularioTurnosAutoridades(
        request.POST if configura_turnos else None,
        eleccion_claustro=eleccion_claustro,
        prefix="configuracion",
    )
    formulario_manual = FormularioAsignacionAutoridad(
        request.POST if asigna_autoridad else None,
        eleccion_claustro=eleccion_claustro,
        prefix="manual",
    )
    formulario_csv = FormularioArchivoAutoridades(
        request.POST if carga_candidatos else None,
        request.FILES if carga_candidatos else None,
        prefix="csv",
    )
    if configura_turnos and formulario_turnos.is_valid():
        formulario_turnos.guardar()
        messages.success(request, f"Turnos de {eleccion_claustro.claustro} actualizados.")
        return redirect(
            "gestionar-autoridades-claustro",
            eleccion_id=eleccion.id,
            claustro_id=eleccion_claustro.id,
        )
    if asigna_autoridad and formulario_manual.is_valid():
        try:
            _, creada = asignar_autoridad(
                formulario_manual.cleaned_data["candidatura"].registro_padron,
                formulario_manual.cleaned_data["mesa"],
                formulario_manual.cleaned_data["turno"],
                request.user,
            )
        except ValidationError as error:
            formulario_manual.add_error(None, error.messages[0])
        else:
            messages.success(request, "Autoridad asignada." if creada else "El elector ya era autoridad de esta mesa.")
            return redirect(
                "gestionar-autoridades-claustro",
                eleccion_id=eleccion.id,
                claustro_id=eleccion_claustro.id,
            )
    if carga_candidatos and formulario_csv.is_valid():
        archivo = formulario_csv.cleaned_data["archivo"]
        cantidad, errores = importar_autoridades(
            archivo.read(),
            eleccion_claustro,
            request.user,
            archivo.name,
        )
        if errores:
            detalle_errores = [
                f"Fila {fila}: {mensaje}" if fila is not None else mensaje
                for fila, mensaje in errores[:3]
            ]
            if len(errores) > 3:
                detalle_errores.append(f"Hay {len(errores) - 3} errores más.")
            formulario_csv.add_error(
                "archivo",
                "No se cargó ningún candidato. " + " ".join(detalle_errores),
            )
        else:
            messages.success(request, f"Se cargaron {cantidad} candidatos desde el CSV.")
            return redirect(
                "gestionar-autoridades-claustro",
                eleccion_id=eleccion.id,
                claustro_id=eleccion_claustro.id,
            )
    autoridades = AsignacionAutoridad.objects.filter(
        mesa__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related("registro_padron__elector", "mesa", "turno", "asignada_por")
    return render(
        request,
        "autoridades/gestion_claustro.html",
        {
            "eleccion": eleccion,
            "eleccion_claustro": eleccion_claustro,
            "formulario_turnos": formulario_turnos,
            "formulario_manual": formulario_manual,
            "formulario_csv": formulario_csv,
            "autoridades": autoridades,
        },
    )


@login_required
def mis_asignaciones_autoridad(request):
    elector = elector_de_identidad(request.user)
    asignaciones = AsignacionAutoridad.objects.select_related("mesa__sede", "turno", "registro_padron__eleccion", "registro_padron__elector")
    if request.user.is_superuser:
        return render(request, "autoridades/mis_asignaciones.html", {"asignaciones": asignaciones, "vista_administrativa": True})
    if elector is not None:
        asignaciones = asignaciones.filter(registro_padron__elector=elector)
        if not asignaciones.exists():
            return HttpResponseForbidden("No tiene asignaciones de autoridad de mesa.")
    elif getattr(request.user, "es_elector", False) or not request.user.asignaciones_rol.filter(rol="autoridad_mesa", activo=True).exists():
        return HttpResponseForbidden("No tiene permiso de autoridad de mesa.")
    else:
        asignaciones = asignaciones.none()
    return render(request, "autoridades/mis_asignaciones.html", {"asignaciones": asignaciones})


@login_required
def responder_autoridad(request, asignacion_id):
    if request.method != "POST":
        raise Http404()
    asignacion = get_object_or_404(AsignacionAutoridad, pk=asignacion_id, registro_padron__elector=elector_de_identidad(request.user))
    responder_asignacion(asignacion, request.POST.get("respuesta") == "aceptar")
    messages.success(request, "La respuesta fue registrada.")
    return redirect("mis-asignaciones-autoridad")


@login_required
def preferencia_autoridad(request, asignacion_id):
    asignacion = get_object_or_404(AsignacionAutoridad.objects.select_related("registro_padron__eleccion"), pk=asignacion_id, registro_padron__elector=elector_de_identidad(request.user))
    preferencia, _ = PreferenciaAutoridad.objects.get_or_create(registro_padron=asignacion.registro_padron)
    formulario = FormularioPreferenciaAutoridad(
        request.POST or None,
        instance=preferencia,
        registro_padron=asignacion.registro_padron,
    )
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "La preferencia fue actualizada.")
        return redirect("mis-asignaciones-autoridad")
    return render(request, "autoridades/preferencia.html", {"asignacion": asignacion, "formulario": formulario})
