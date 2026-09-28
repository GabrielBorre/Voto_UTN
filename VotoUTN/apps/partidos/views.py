import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.elecciones.models import Eleccion
from apps.auditoria.services import registrar_evento
from apps.partidos.forms import (
    FormularioCandidato,
    FormularioHabilitacionPuesto,
    FormularioImportacionCandidaturas,
    FormularioListaCandidatos,
    FormularioParticipacionPartido,
    FormularioPuestoEleccion,
)
from apps.partidos.models import Candidato, ImportacionCandidaturas, ListaCandidatos, ParticipacionPartido, PuestoEleccion
from apps.partidos.services import (
    ENCABEZADOS_CANDIDATURAS,
    confirmar_importacion_candidaturas,
    guardar_con_validacion,
    previsualizar_importacion_candidaturas,
)
from apps.usuarios.permisos import puede_administrar_elecciones


def _tiene_permiso(request, eleccion):
    return puede_administrar_elecciones(request.user, eleccion)


@login_required
def gestionar_partidos(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar partidos y candidatos.")

    formulario_puesto = FormularioHabilitacionPuesto(request.POST or None, eleccion=eleccion, prefix="puesto")
    formulario_participacion = FormularioParticipacionPartido(request.POST or None, eleccion=eleccion, prefix="presentacion")
    accion = request.POST.get("accion")
    if request.method == "POST" and accion == "configurar_puesto" and formulario_puesto.is_valid():
        configuraciones = formulario_puesto.guardar()
        for configuracion in configuraciones:
            registrar_evento(
                accion="configurar_puesto_eleccion",
                entidad=configuracion._meta.label,
                entidad_id=configuracion.pk,
                eleccion=eleccion,
                request=request,
            )
        messages.success(request, f"El puesto fue habilitado en {len(configuraciones)} alcances.")
        return redirect("gestionar-partidos", eleccion_id=eleccion.id)
    if request.method == "POST" and accion == "crear_presentacion" and formulario_participacion.is_valid():
        guardar_con_validacion(formulario_participacion, eleccion=eleccion)
        messages.success(request, "La presentación de lista fue creada.")
        return redirect("gestionar-partidos", eleccion_id=eleccion.id)

    participaciones = eleccion.partidos_participantes.select_related("partido", "eleccion_claustro__claustro").annotate(
        cantidad_listas=Count("listas", distinct=True),
        cantidad_candidatos=Count("listas__candidatos", distinct=True),
    )
    puestos = PuestoEleccion.objects.filter(eleccion_claustro__eleccion=eleccion).select_related(
        "puesto__organo", "eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento",
    )
    return render(
        request,
        "partidos/gestion.html",
        {
            "eleccion": eleccion,
            "participaciones": participaciones,
            "formulario_puesto": formulario_puesto,
            "formulario_participacion": formulario_participacion,
            "puestos": puestos,
        },
    )


@login_required
def importar_candidaturas(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para importar candidaturas.")
    formulario = FormularioImportacionCandidaturas(request.POST or None, request.FILES or None)
    importacion = None
    if request.method == "POST" and formulario.is_valid():
        importacion = previsualizar_importacion_candidaturas(
            eleccion=eleccion,
            archivo=formulario.cleaned_data["archivo"],
            usuario=request.user,
        )
        if importacion.errores:
            messages.error(request, "El archivo contiene errores y no puede confirmarse.")
        else:
            messages.success(request, "La previsualización está lista. Revise los datos antes de confirmar.")
    return render(
        request,
        "partidos/importar_candidaturas.html",
        {"eleccion": eleccion, "formulario": formulario, "importacion": importacion},
    )


@login_required
def editar_puesto_eleccion(request, eleccion_id, puesto_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar puestos de esta elección.")
    puesto = get_object_or_404(PuestoEleccion, pk=puesto_id, eleccion_claustro__eleccion=eleccion)
    formulario = FormularioPuestoEleccion(request.POST or None, instance=puesto, eleccion=eleccion)
    if request.method == "POST" and formulario.is_valid():
        guardar_con_validacion(formulario)
        messages.success(request, "La configuración del puesto fue actualizada.")
        return redirect("gestionar-partidos", eleccion_id=eleccion.pk)
    return render(
        request,
        "partidos/puesto_formulario.html",
        {"eleccion": eleccion, "puesto": puesto, "formulario": formulario},
    )


@login_required
def cambiar_estado_puesto_eleccion(request, eleccion_id, puesto_id):
    puesto = get_object_or_404(
        PuestoEleccion.objects.select_related("eleccion_claustro__eleccion"),
        pk=puesto_id,
        eleccion_claustro__eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, puesto.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar puestos de esta elección.")
    return _cambiar_estado(request, puesto, "activo", "gestionar-partidos", eleccion_id=eleccion_id)


@login_required
def confirmar_importacion(request, eleccion_id, importacion_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para importar candidaturas.")
    importacion = get_object_or_404(ImportacionCandidaturas, pk=importacion_id, eleccion=eleccion)
    try:
        resultado = confirmar_importacion_candidaturas(importacion)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("importar-candidaturas", eleccion_id=eleccion.pk)
    registrar_evento(
        accion="confirmar_importacion_candidaturas",
        entidad=importacion._meta.label,
        entidad_id=importacion.pk,
        eleccion=eleccion,
        request=request,
        datos_nuevos=resultado,
    )
    messages.success(request, f"Se confirmaron {resultado['filas']} candidaturas en {resultado['presentaciones']} presentaciones.")
    return redirect("gestionar-partidos", eleccion_id=eleccion.pk)


@login_required
def descargar_plantilla_candidaturas(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar esta plantilla.")
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="plantilla-candidaturas-{eleccion.pk}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta, delimiter=";")
    escritor.writerow(ENCABEZADOS_CANDIDATURAS)
    return respuesta


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
        "puesto_eleccion__puesto__organo",
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
            "puesto_eleccion__puesto__organo",
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
