from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.notificaciones.forms import FormularioEnviarNotificacion, FormularioPlantillaNotificacion
from apps.notificaciones.services import crear_envios
from apps.usuarios.permisos import puede_administrar_parametros


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
    return render(
        request,
        "notificaciones/gestion.html",
        {
            "formulario_plantilla": formulario_plantilla,
            "formulario_envio": formulario_envio,
            "plantillas": PlantillaNotificacion.objects.all(),
            "envios": EnvioNotificacion.objects.select_related("destinatario", "eleccion")[:20],
        },
    )


@login_required
def mis_notificaciones(request):
    relacion_notificaciones = getattr(request.user, "notificaciones", None)
    notificaciones = relacion_notificaciones.all() if relacion_notificaciones is not None else EnvioNotificacion.objects.none()
    return render(request, "notificaciones/mis_notificaciones.html", {"notificaciones": notificaciones})


@login_required
def leer_notificacion(request, notificacion_id):
    if not hasattr(request.user, "notificaciones"):
        return HttpResponseForbidden("No tiene notificaciones asociadas.")
    notificacion = get_object_or_404(EnvioNotificacion, pk=notificacion_id, destinatario=request.user)
    if notificacion.leida_en is None:
        notificacion.leida_en = timezone.now()
        notificacion.save(update_fields=("leida_en",))
    return render(request, "notificaciones/detalle.html", {"notificacion": notificacion})
