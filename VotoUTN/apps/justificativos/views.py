from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.elecciones.models import Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.justificativos.forms import FormularioJustificativo, FormularioResolucionJustificativo
from apps.padron.models import Elector
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import es_administrativo_junta, puede_revisar_justificativo


@login_required
def mis_justificativos(request):
    perfil = getattr(request.user, "perfil_electoral", None)
    elector = perfil.elector if perfil and perfil.elector_id else None
    if elector is None:
        dni = getattr(request.user, "dni", None)
        if dni:
            elector = Elector.objects.filter(dni=dni).first()
    if elector is None:
        return HttpResponseForbidden("No existe un elector asociado a esta identidad.")
    formulario = FormularioJustificativo(request.POST or None, request.FILES or None, elector=elector)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "El justificativo fue presentado para revision.")
        return redirect("mis-justificativos")
    justificativos = JustificativoAusencia.objects.select_related("registro_padron__eleccion", "tipo")
    justificativos = justificativos.filter(registro_padron__elector=elector)
    return render(request, "justificativos/mis_justificativos.html", {"formulario": formulario, "justificativos": justificativos})


@login_required
def gestionar_justificativos(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_revisar_justificativo(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para revisar justificativos.")
    justificativos = JustificativoAusencia.objects.filter(
        registro_padron__eleccion=eleccion,
    ).select_related("registro_padron__elector", "tipo", "resuelta_por").order_by("-presentada_en")
    resumen = justificativos.aggregate(
        total=Count("id"),
        pendientes=Count("id", filter=Q(estado=JustificativoAusencia.Estado.PENDIENTE)),
        aprobados=Count("id", filter=Q(estado=JustificativoAusencia.Estado.APROBADO)),
        rechazados=Count("id", filter=Q(estado=JustificativoAusencia.Estado.RECHAZADO)),
    )
    return render(
        request,
        "justificativos/gestion.html",
        {"eleccion": eleccion, "justificativos": justificativos, "resumen": resumen},
    )


@login_required
def bandeja_justificativos(request):
    es_administrador_sistema = request.user.is_superuser or AsignacionRol.objects.filter(
        usuario=request.user,
        activo=True,
        rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA,
    ).exists()
    if es_administrador_sistema or es_administrativo_junta(request.user):
        justificativos = JustificativoAusencia.objects.all()
    else:
        elecciones = (
            AsignacionRol.objects.filter(
                usuario=request.user,
                activo=True,
                rol__in=(AsignacionRol.Rol.ADMINISTRADOR_JUNTA, AsignacionRol.Rol.ADMINISTRATIVO_JUNTA),
            )
            .exclude(eleccion__isnull=True)
            .values_list("eleccion_id", flat=True)
        )
        justificativos = JustificativoAusencia.objects.filter(registro_padron__eleccion_id__in=elecciones)
    tiene_permiso = es_administrador_sistema or es_administrativo_junta(request.user) or AsignacionRol.objects.filter(
            usuario=request.user,
            activo=True,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        ).exists()
    if not tiene_permiso:
        return HttpResponseForbidden("No tiene permiso para revisar justificativos.")
    justificativos = justificativos.select_related("registro_padron__eleccion", "registro_padron__elector", "tipo")
    return render(request, "justificativos/bandeja.html", {"justificativos": justificativos})


@login_required
def resolver_justificativo(request, justificativo_id):
    justificativo = get_object_or_404(
        JustificativoAusencia.objects.select_related(
            "registro_padron__eleccion",
            "registro_padron__elector",
            "tipo",
            "resuelta_por",
        ),
        pk=justificativo_id,
    )
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
    return render(request, "justificativos/resolver.html", {"justificativo": justificativo, "formulario": formulario})
