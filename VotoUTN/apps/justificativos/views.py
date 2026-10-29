from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.elecciones.models import ESTADOS_ELECCION_NO_CERRADOS, Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.justificativos.forms import FormularioJustificativo, FormularioResolucionJustificativo
from apps.notificaciones.services import crear_notificacion_resultado_justificativo, enviar_notificacion
from apps.padron.models import Elector, RegistroPadron
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
    eleccion = (
        Eleccion.objects.filter(estado__in=ESTADOS_ELECCION_NO_CERRADOS)
        .order_by("-fecha_inicio", "-id")
        .first()
    )
    registro_padron = None
    if eleccion is not None:
        registro_padron = (
            RegistroPadron.objects.filter(elector=elector, eleccion=eleccion, activo=True)
            .select_related("eleccion")
            .first()
        )
    estado_habilitado = bool(
        eleccion
        and eleccion.estado in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO)
    )
    formulario = FormularioJustificativo(
        request.POST or None,
        request.FILES or None,
        registro_padron=registro_padron,
    )
    if request.method == "POST" and not estado_habilitado:
        messages.error(
            request,
            "La presentación de justificativos está habilitada únicamente para elecciones publicadas o en curso.",
        )
        return redirect("mis-justificativos")
    if request.method == "POST" and registro_padron is None:
        messages.error(request, "No tenés un padrón activo para la elección actual.")
        return redirect("mis-justificativos")
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "El justificativo fue presentado para revision.")
        return redirect("mis-justificativos")
    justificativos = JustificativoAusencia.objects.select_related("registro_padron__eleccion", "tipo")
    justificativos = justificativos.filter(registro_padron__elector=elector).order_by("-presentada_en", "-pk")
    return render(
        request,
        "justificativos/mis_justificativos.html",
        {
            "eleccion": eleccion,
            "registro_padron": registro_padron,
            "estado_habilitado": estado_habilitado,
            "formulario": formulario,
            "puede_presentar": estado_habilitado and bool(formulario.fields["ausencia"].choices),
            "justificativos": justificativos,
        },
    )


@login_required
def gestionar_justificativos(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_revisar_justificativo(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para revisar justificativos.")
    pestana = request.GET.get("pestana")
    if pestana not in ("electores", "autoridades"):
        pestana = "electores"
    ausencia = JustificativoAusencia.Ausencia.AUTORIDAD if pestana == "autoridades" else JustificativoAusencia.Ausencia.VOTAR
    justificativos = JustificativoAusencia.objects.filter(
        registro_padron__eleccion=eleccion,
        ausencia=ausencia,
    ).select_related("registro_padron__elector", "tipo", "resuelta_por").order_by("-presentada_en")
    resumen = justificativos.aggregate(
        total=Count("id"),
        pendientes=Count("id", filter=Q(estado=JustificativoAusencia.Estado.PENDIENTE)),
        aprobados=Count("id", filter=Q(estado=JustificativoAusencia.Estado.APROBADO)),
        rechazados=Count("id", filter=Q(estado=JustificativoAusencia.Estado.RECHAZADO)),
    )
    estado = request.GET.get("estado", "")
    if estado in JustificativoAusencia.Estado.values:
        justificativos = justificativos.filter(estado=estado)
    else:
        estado = ""
    return render(
        request,
        "justificativos/gestion.html",
        {
            "eleccion": eleccion,
            "justificativos": justificativos,
            "resumen": resumen,
            "pestana": pestana,
            "estado": estado,
            "estados": JustificativoAusencia.Estado.choices,
            "nav_en_historial": eleccion.estado == Eleccion.Estado.FINALIZADA,
        },
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
    eleccion = justificativo.registro_padron.eleccion
    if not puede_revisar_justificativo(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para resolver este justificativo.")
    if request.method == "POST" and eleccion.estado == Eleccion.Estado.FINALIZADA:
        return HttpResponseForbidden("No se pueden modificar justificativos de elecciones del historial.")
    formulario = FormularioResolucionJustificativo(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            justificativo = (
                JustificativoAusencia.objects.select_for_update(of=("self",))
                .select_related("registro_padron__eleccion", "registro_padron__elector")
                .get(pk=justificativo.pk)
            )
            estaba_pendiente = justificativo.estado == JustificativoAusencia.Estado.PENDIENTE
            justificativo.estado = formulario.cleaned_data["estado"]
            justificativo.observacion_resolucion = formulario.cleaned_data["observacion_resolucion"]
            justificativo.resuelta_por = request.user
            justificativo.resuelta_en = timezone.now()
            justificativo.save(update_fields=("estado", "observacion_resolucion", "resuelta_por", "resuelta_en"))
            envio = crear_notificacion_resultado_justificativo(justificativo) if estaba_pendiente else None
        if envio is not None:
            correo_enviado = enviar_notificacion(envio)
            if correo_enviado:
                messages.success(request, "El justificativo fue resuelto y se notificó al elector por correo.")
            else:
                messages.warning(request, "El justificativo fue resuelto y la notificación está disponible en la web, pero no se pudo enviar el correo al elector.")
        else:
            messages.success(request, "El justificativo fue actualizado.")
        return redirect("gestionar-justificativos", eleccion_id=justificativo.registro_padron.eleccion_id)
    return render(
        request,
        "justificativos/resolver.html",
        {
            "justificativo": justificativo,
            "formulario": formulario,
            "nav_en_historial": eleccion.estado == Eleccion.Estado.FINALIZADA,
        },
    )
