from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.models import Eleccion
from apps.partidos.forms import FormularioCandidato, FormularioListaCandidatos, FormularioParticipacionPartido, FormularioPartido
from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido
from apps.partidos.services import guardar_con_validacion
from apps.usuarios.permisos import puede_administrar_elecciones


def _tiene_permiso(request, eleccion):
    return puede_administrar_elecciones(request.user, eleccion)


@login_required
def gestionar_partidos(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar partidos y candidatos.")

    formulario_partido = FormularioPartido(request.POST or None, prefix="partido")
    formulario_participacion = FormularioParticipacionPartido(request.POST or None, eleccion=eleccion, prefix="participacion")
    accion = request.POST.get("accion")
    if request.method == "POST" and accion == "crear_partido" and formulario_partido.is_valid():
        formulario_partido.save()
        messages.success(request, "El partido fue creado.")
        return redirect("gestionar-partidos", eleccion_id=eleccion.id)
    if request.method == "POST" and accion == "incorporar_partido" and formulario_participacion.is_valid():
        guardar_con_validacion(formulario_participacion, eleccion=eleccion)
        messages.success(request, "El partido fue incorporado a la eleccion.")
        return redirect("gestionar-partidos", eleccion_id=eleccion.id)

    participaciones = eleccion.partidos_participantes.select_related("partido").annotate(
        cantidad_listas=Count("listas", distinct=True),
        cantidad_candidatos=Count("listas__candidatos", distinct=True),
    )
    return render(
        request,
        "partidos/gestion.html",
        {
            "eleccion": eleccion,
            "participaciones": participaciones,
            "formulario_partido": formulario_partido,
            "formulario_participacion": formulario_participacion,
        },
    )


@login_required
def detalle_participacion(request, eleccion_id, participacion_id):
    participacion = get_object_or_404(
        ParticipacionPartido.objects.select_related("eleccion", "partido"),
        pk=participacion_id,
        eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta participacion.")
    formulario = FormularioListaCandidatos(request.POST or None, participacion=participacion)
    if request.method == "POST" and formulario.is_valid():
        guardar_con_validacion(formulario, participacion=participacion)
        messages.success(request, "La lista de candidatos fue creada.")
        return redirect("detalle-participacion-partido", eleccion_id=eleccion_id, participacion_id=participacion.id)
    listas = participacion.listas.select_related(
        "eleccion_claustro__claustro",
        "eleccion_claustro_departamento__departamento",
    ).prefetch_related("candidatos")
    return render(request, "partidos/detalle_participacion.html", {"participacion": participacion, "listas": listas, "formulario": formulario})


@login_required
def detalle_lista(request, eleccion_id, lista_id):
    lista = get_object_or_404(
        ListaCandidatos.objects.select_related(
            "participacion__eleccion",
            "participacion__partido",
            "eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
        ),
        pk=lista_id,
        participacion__eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta lista.")
    formulario = FormularioCandidato(request.POST or None, lista=lista)
    if request.method == "POST" and formulario.is_valid():
        guardar_con_validacion(formulario, lista=lista)
        messages.success(request, "El candidato fue agregado.")
        return redirect("detalle-lista-candidatos", eleccion_id=eleccion_id, lista_id=lista.id)
    return render(request, "partidos/detalle_lista.html", {"lista": lista, "candidatos": lista.candidatos.all(), "formulario": formulario})


@login_required
def editar_candidato(request, eleccion_id, candidato_id):
    candidato = get_object_or_404(
        Candidato.objects.select_related("lista__participacion__eleccion", "lista__participacion__partido"),
        pk=candidato_id,
        lista__participacion__eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, candidato.lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para editar este candidato.")
    formulario = FormularioCandidato(request.POST or None, instance=candidato, lista=candidato.lista)
    if request.method == "POST" and formulario.is_valid():
        guardar_con_validacion(formulario, lista=candidato.lista)
        messages.success(request, "El candidato fue actualizado.")
        return redirect("detalle-lista-candidatos", eleccion_id=eleccion_id, lista_id=candidato.lista_id)
    return render(request, "partidos/candidato_formulario.html", {"candidato": candidato, "formulario": formulario})


def _cambiar_estado(request, objeto, campo, destino, **destino_kwargs):
    if request.method != "POST":
        raise Http404()
    setattr(objeto, campo, request.POST.get("activo") == "1")
    objeto.save(update_fields=(campo,))
    messages.success(request, "El estado fue actualizado.")
    return redirect(destino, **destino_kwargs)


@login_required
def cambiar_estado_participacion(request, eleccion_id, participacion_id):
    participacion = get_object_or_404(ParticipacionPartido.objects.select_related("eleccion"), pk=participacion_id, eleccion_id=eleccion_id)
    if not _tiene_permiso(request, participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar esta participacion.")
    return _cambiar_estado(request, participacion, "activa", "gestionar-partidos", eleccion_id=eleccion_id)


@login_required
def cambiar_estado_lista(request, eleccion_id, lista_id):
    lista = get_object_or_404(ListaCandidatos.objects.select_related("participacion__eleccion"), pk=lista_id, participacion__eleccion_id=eleccion_id)
    if not _tiene_permiso(request, lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar esta lista.")
    return _cambiar_estado(
        request,
        lista,
        "activa",
        "detalle-participacion-partido",
        eleccion_id=eleccion_id,
        participacion_id=lista.participacion_id,
    )


@login_required
def cambiar_estado_candidato(request, eleccion_id, candidato_id):
    candidato = get_object_or_404(Candidato.objects.select_related("lista__participacion__eleccion"), pk=candidato_id, lista__participacion__eleccion_id=eleccion_id)
    if not _tiene_permiso(request, candidato.lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar este candidato.")
    return _cambiar_estado(
        request,
        candidato,
        "activo",
        "detalle-lista-candidatos",
        eleccion_id=eleccion_id,
        lista_id=candidato.lista_id,
    )
