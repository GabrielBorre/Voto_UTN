from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.autoridades.forms import FormularioArchivoAutoridades, FormularioAsignacionAutoridad, FormularioPreferenciaAutoridad
from apps.autoridades.services import asignar_autoridad, importar_autoridades, responder_asignacion
from apps.autoridades.models import AsignacionAutoridad, PreferenciaAutoridad
from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_administrar_elecciones
from apps.usuarios.services import elector_de_identidad


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
    return render(request, "autoridades/gestion.html", {"eleccion": eleccion, "formulario_manual": formulario_manual, "formulario_csv": formulario_csv, "autoridades": autoridades})


@login_required
def mis_asignaciones_autoridad(request):
    elector = elector_de_identidad(request.user)
    asignaciones = AsignacionAutoridad.objects.select_related("mesa__sede", "mesa__turno", "registro_padron__eleccion", "registro_padron__elector")
    if request.user.is_superuser:
        return render(request, "autoridades/mis_asignaciones.html", {"asignaciones": asignaciones, "vista_administrativa": True})
    if elector is not None:
        asignaciones = asignaciones.filter(registro_padron__elector=elector)
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
    formulario = FormularioPreferenciaAutoridad(request.POST or None, instance=preferencia, eleccion=asignacion.registro_padron.eleccion, registro_padron=asignacion.registro_padron)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "La preferencia fue actualizada.")
        return redirect("mis-asignaciones-autoridad")
    return render(request, "autoridades/preferencia.html", {"asignacion": asignacion, "formulario": formulario})
