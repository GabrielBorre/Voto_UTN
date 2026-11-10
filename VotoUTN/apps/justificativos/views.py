from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.elecciones.models import ESTADOS_ELECCION_NO_CERRADOS, Eleccion
from apps.justificativos.models import JustificativoAusencia
from apps.justificativos.forms import FormularioJustificativo, FormularioResolucionJustificativo
from apps.justificativos.services import (
    anular_participacion_por_reclamo,
    puede_presentar_justificativo_electoral,
    restaurar_participacion_anulada,
    validar_comprobante,
)
from apps.notificaciones.services import crear_notificacion_resultado_justificativo, enviar_notificacion
from apps.padron.models import Elector, RegistroPadron
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import (
    es_administrativo_junta,
    puede_consultar_historial_electoral,
    puede_revisar_justificativo,
)
from apps.usuarios.services import elector_de_identidad


@login_required
def mis_justificativos(request):
    perfil = getattr(request.user, "perfil_electoral", None)
    eleccion = (
        Eleccion.objects.filter(estado__in=ESTADOS_ELECCION_NO_CERRADOS)
        .order_by("-fecha_inicio", "-id")
        .first()
    )
    registro_padron = None
    dni = getattr(request.user, "dni", None)
    if perfil is not None and perfil.elector_id:
        dni = perfil.elector.dni
    if eleccion is not None:
        registro_padron = (
            RegistroPadron.objects.filter(dni=dni, eleccion=eleccion, activo=True)
            .select_related("eleccion", "elector")
            .first()
        )
    elector = registro_padron.elector if registro_padron else None
    if elector is None:
        return HttpResponseForbidden("No existe un elector asociado a esta identidad en la elección actual.")
    estado_habilitado = bool(
        eleccion
        and eleccion.estado in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO)
    )
    formulario = FormularioJustificativo(
        request.POST or None,
        request.FILES or None,
        registro_padron=registro_padron,
        initial={"ausencia": JustificativoAusencia.Ausencia.AUTORIDAD} if request.GET.get("ausencia") == "autoridad" else None,
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
        try:
            justificativo = formulario.save()
            validar_comprobante(justificativo)
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
            messages.success(request, "El justificativo fue presentado para revision.")
            return redirect("mis-justificativos")
    justificativos = JustificativoAusencia.objects.select_related("registro_padron__eleccion", "tipo")
    justificativos = justificativos.filter(registro_padron__eleccion=eleccion).order_by("-presentada_en", "-pk")
    return render(
        request,
        "justificativos/mis_justificativos.html",
        {
            "eleccion": eleccion,
            "registro_padron": registro_padron,
            "estado_habilitado": estado_habilitado,
            "formulario": formulario,
            "puede_presentar": estado_habilitado and bool(formulario.fields["ausencia"].choices),
            "puede_presentar_justificativo_electoral": bool(
                registro_padron and puede_presentar_justificativo_electoral(registro_padron)
            ),

            "justificativos": justificativos,
        },
    )


@login_required
def detalle_justificativo_elector(request, justificativo_id):
    elector = elector_de_identidad(request.user)
    if not puede_consultar_historial_electoral(request.user, elector):
        return HttpResponseForbidden("No tiene permiso para consultar justificativos electorales.")
    justificativo = get_object_or_404(
        JustificativoAusencia.objects.select_related(
            "registro_padron__eleccion",
            "registro_padron__elector",
            "tipo",
            "resuelta_por",
        ),
        pk=justificativo_id,
        registro_padron__elector=elector,
        ausencia=JustificativoAusencia.Ausencia.VOTAR,
    )
    return render(
        request,
        "justificativos/detalle_elector.html",
        {
            "justificativo": justificativo,
            "documento_es_pdf": justificativo.documento.name.lower().endswith(".pdf")
            if justificativo.documento
            else False,
            "url_documento": (
                reverse("documento-justificativo-elector", args=(justificativo.pk,))
                if justificativo.documento
                else None
            ),
        },
    )


@login_required
def documento_justificativo_elector(request, justificativo_id):
    elector = elector_de_identidad(request.user)
    if not puede_consultar_historial_electoral(request.user, elector):
        return HttpResponseForbidden("No tiene permiso para consultar justificativos electorales.")
    justificativo = get_object_or_404(
        JustificativoAusencia.objects.filter(
            registro_padron__elector=elector,
            ausencia=JustificativoAusencia.Ausencia.VOTAR,
        ),
        pk=justificativo_id,
    )
    if not justificativo.documento:
        raise Http404("El justificativo no tiene documentación adjunta.")
    return _respuesta_documento_privado(justificativo)


@login_required
def documento_justificativo_gestion(request, justificativo_id):
    justificativo = get_object_or_404(
        JustificativoAusencia.objects.select_related("registro_padron__eleccion"),
        pk=justificativo_id,
    )
    if not puede_revisar_justificativo(request.user, justificativo.registro_padron.eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar este justificativo.")
    if not justificativo.documento:
        raise Http404("El justificativo no tiene documentación adjunta.")
    return _respuesta_documento_privado(justificativo)


@login_required
def documento_justificativo_por_archivo(request, nombre_archivo):
    justificativo = get_object_or_404(
        JustificativoAusencia.objects.select_related("registro_padron__eleccion"),
        documento=f"justificativos/{nombre_archivo}",
    )
    elector = elector_de_identidad(request.user)
    es_titular = (
        justificativo.registro_padron.elector_id == getattr(elector, "pk", None)
        and puede_consultar_historial_electoral(request.user, elector)
    )
    puede_revisar = puede_revisar_justificativo(
        request.user,
        justificativo.registro_padron.eleccion,
    )
    if not es_titular and not puede_revisar:
        raise Http404("No existe el documento solicitado.")
    return _respuesta_documento_privado(justificativo)


def _respuesta_documento_privado(justificativo):
    respuesta = FileResponse(justificativo.documento.open("rb"), as_attachment=False)
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


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
    if request.method == "POST" and request.POST.get("accion") == "revalidar":
        if justificativo.reclamo_participacion:
            validar_comprobante(justificativo)
            messages.success(request, "Se volvió a validar el comprobante.")
        return redirect("resolver-justificativo", justificativo_id=justificativo.pk)
    formulario = FormularioResolucionJustificativo(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        from apps.justificativos.services import resolver_justificativo as resolver
        try:
            with transaction.atomic():
                estaba_pendiente = resolver(
                    justificativo, estado=formulario.cleaned_data["estado"],
                    observacion=formulario.cleaned_data["observacion_resolucion"], usuario=request.user,
                )
                if justificativo.reclamo_participacion:
                    if justificativo.estado == JustificativoAusencia.Estado.APROBADO:
                        anular_participacion_por_reclamo(justificativo, usuario=request.user, request=request)
                    else:
                        restaurar_participacion_anulada(justificativo, usuario=request.user, request=request)
                envio = crear_notificacion_resultado_justificativo(justificativo) if estaba_pendiente else None
        except ValidationError as error:
            formulario.add_error(None, error)
        else:
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
