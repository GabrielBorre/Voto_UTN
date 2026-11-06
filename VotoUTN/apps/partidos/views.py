import csv
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from apps.elecciones.models import Eleccion
from apps.elecciones.models import EleccionClaustro
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
    ENCABEZADOS_CANDIDATOS_LISTA,
    confirmar_candidatos_lista,
    confirmar_importacion_candidaturas,
    crear_presentacion_con_puestos,
    guardar_con_validacion,
    previsualizar_candidatos_lista,
    previsualizar_importacion_candidaturas,
    buscar_elector_candidato,
)
from apps.usuarios.permisos import puede_configurar_eleccion


def _tiene_permiso(request, eleccion):
    return puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD"))


def _url_gestion(eleccion_id, participacion_id=None, lista_id=None, pestana_candidatos=None):
    url = reverse("gestionar-partidos", args=(eleccion_id,))
    if participacion_id:
        url = reverse("detalle-participacion-partido", args=(eleccion_id, participacion_id))
        parametros = []
        if lista_id:
            parametros.append(f"puesto={lista_id}")
        if pestana_candidatos:
            parametros.append(f"pestana_candidatos={pestana_candidatos}")
        if parametros:
            url += f"?{'&'.join(parametros)}"
        url += "#candidaturas"
    return url


def _id_opcional(valor):
    if not valor:
        return None
    if not valor.isdecimal():
        raise Http404()
    return int(valor)


@login_required
@require_POST
@never_cache
def buscar_elector(request, eleccion_id, lista_id):
    lista = get_object_or_404(
        ListaCandidatos.objects.select_related("participacion__eleccion", "puesto_eleccion"),
        pk=lista_id, participacion__eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para consultar este padrón.")
    try:
        elector = buscar_elector_candidato(
            eleccion=lista.participacion.eleccion, puesto=lista.puesto_eleccion or lista,
            tipo_documento=request.POST.get("tipo_documento"), documento=request.POST.get("documento"),
        )
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    return JsonResponse({"nombre": elector.nombre_completo})


@login_required
def gestionar_partidos(request, eleccion_id, participacion_id=None):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not _tiene_permiso(request, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar partidos y candidatos.")

    pantalla_candidatos = participacion_id is not None
    claustro_id = _id_opcional(request.GET.get("claustro"))
    claustro_seleccionado = (
        get_object_or_404(
            EleccionClaustro.objects.select_related("claustro"),
            pk=claustro_id,
            eleccion=eleccion,
        )
        if claustro_id
        else None
    )
    pestana_solicitada = request.GET.get("pestana")
    pestana = pestana_solicitada if pestana_solicitada in ("puesto", "candidatos") else "lista"
    accion = request.POST.get("accion") or (
        "vincular_puesto" if pantalla_candidatos and request.method == "POST" and "puesto_eleccion" in request.POST else None
    )
    participacion_id = participacion_id or _id_opcional(request.GET.get("lista"))
    participacion_seleccionada = None
    if participacion_id:
        participacion_seleccionada = get_object_or_404(
            ParticipacionPartido.objects.select_related("eleccion_claustro__claustro"),
            pk=participacion_id, eleccion=eleccion,
        )
    asociaciones = []
    asociacion_seleccionada = None
    candidato_en_edicion = None
    if participacion_seleccionada:
        asociaciones = list(participacion_seleccionada.listas.select_related(
            "puesto_eleccion__puesto__organo", "eleccion_claustro_departamento__departamento",
        ).prefetch_related("candidatos"))
        asociacion_id = _id_opcional(request.GET.get("puesto"))
        if asociacion_id:
            asociacion_seleccionada = next((item for item in asociaciones if item.pk == asociacion_id), None)
            if asociacion_seleccionada is None:
                raise Http404()
        elif asociaciones:
            asociacion_seleccionada = asociaciones[0]
        candidato_id = _id_opcional(request.GET.get("editar"))
        if candidato_id:
            if asociacion_seleccionada is None:
                raise Http404()
            candidato_en_edicion = get_object_or_404(
                Candidato, pk=candidato_id, lista=asociacion_seleccionada,
            )
    pestana_candidatos = (
        "csv"
        if request.GET.get("pestana_candidatos") == "csv"
        or accion in ("previsualizar_candidatos", "confirmar_candidatos")
        else "manual"
    )
    if candidato_en_edicion:
        pestana_candidatos = "manual"

    formulario_puesto = FormularioHabilitacionPuesto(
        request.POST if accion == "configurar_puesto" else None,
        eleccion=eleccion,
        claustro_objetivo=claustro_seleccionado,
        prefix="puesto",
    )
    formulario_participacion = FormularioParticipacionPartido(
        request.POST if accion == "crear_presentacion" else None,
        eleccion=eleccion,
        prefix="presentacion",
        initial={"eleccion_claustro": claustro_seleccionado.pk} if claustro_seleccionado else None,
    )
    formulario_vincular = FormularioListaCandidatos(
        request.POST if accion == "vincular_puesto" else None,
        participacion=participacion_seleccionada,
    ) if participacion_seleccionada else None
    formulario_candidato = FormularioCandidato(
        request.POST if accion in ("agregar_candidato", "guardar_candidato") else None,
        instance=candidato_en_edicion,
        lista=asociacion_seleccionada,
    ) if asociacion_seleccionada else None
    formulario_csv = FormularioImportacionCandidaturas(
        request.POST if accion == "previsualizar_candidatos" else None,
        request.FILES if accion == "previsualizar_candidatos" else None,
    ) if participacion_seleccionada else None
    importacion = None
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
        if claustro_seleccionado:
            return redirect(
                f"{reverse('gestionar-partidos', args=(eleccion.id,))}"
                f"?claustro={claustro_seleccionado.id}&pestana=puesto"
            )
        return redirect("gestionar-partidos", eleccion_id=eleccion.id)
    if request.method == "POST" and accion == "crear_presentacion" and formulario_participacion.is_valid():
        participacion, listas, configuraciones_creadas = crear_presentacion_con_puestos(
            formulario_participacion, eleccion=eleccion,
            codigo_presentacion=f"MAN-{uuid4().hex}",
        )
        for configuracion in configuraciones_creadas:
            registrar_evento(
                accion="configurar_puesto_eleccion",
                entidad=configuracion._meta.label,
                entidad_id=configuracion.pk,
                eleccion=eleccion,
                request=request,
            )
        for lista in listas:
            registrar_evento(
                accion="vincular_puesto_a_presentacion",
                entidad=lista._meta.label,
                entidad_id=lista.pk,
                eleccion=eleccion,
                request=request,
                datos_nuevos={"participacion": participacion.pk, "puesto_eleccion": lista.puesto_eleccion_id},
            )
        if listas:
            messages.success(request, "La lista y sus puestos fueron creados. Ya podés cargar los candidatos.")
            return redirect(_url_gestion(eleccion.id, participacion.id, listas[0].id))
        messages.success(request, "La lista fue creada. Ahora podés elegir sus puestos y cargar candidatos.")
        return redirect(_url_gestion(eleccion.id, participacion.id))
    if request.method == "POST" and accion == "vincular_puesto" and formulario_vincular and formulario_vincular.is_valid():
        asociacion = guardar_con_validacion(formulario_vincular, participacion=participacion_seleccionada)
        messages.success(request, "El puesto fue agregado a la lista.")
        return redirect(_url_gestion(eleccion.id, participacion_id, asociacion.id))
    if request.method == "POST" and accion in ("agregar_candidato", "guardar_candidato"):
        if not formulario_candidato or (accion == "guardar_candidato") != bool(candidato_en_edicion):
            raise Http404()
        if formulario_candidato.is_valid():
            guardar_con_validacion(formulario_candidato, lista=asociacion_seleccionada)
            messages.success(request, "La persona candidata fue actualizada." if candidato_en_edicion else "La persona candidata fue agregada.")
            return redirect(
                _url_gestion(
                    eleccion.id,
                    participacion_id,
                    asociacion_seleccionada.id,
                    pestana_candidatos="manual",
                )
            )
    if request.method == "POST" and accion == "previsualizar_candidatos" and formulario_csv and formulario_csv.is_valid():
        if not asociacion_seleccionada:
            raise Http404()
        importacion = previsualizar_candidatos_lista(
            lista=asociacion_seleccionada,
            archivo=formulario_csv.cleaned_data["archivo"], usuario=request.user,
        )
    if request.method == "POST" and accion == "confirmar_candidatos" and participacion_seleccionada:
        if not asociacion_seleccionada:
            raise Http404()
        importacion = get_object_or_404(
            ImportacionCandidaturas, pk=_id_opcional(request.POST.get("importacion_id")), eleccion=eleccion,
        )
        try:
            cantidad = confirmar_candidatos_lista(importacion, asociacion_seleccionada)
        except (ValidationError, ListaCandidatos.DoesNotExist) as error:
            messages.error(request, f"No se pudo confirmar la importación: {error}")
        else:
            registrar_evento(
                accion="confirmar_importacion_candidatos_lista",
                entidad=importacion._meta.label,
                entidad_id=importacion.pk,
                eleccion=eleccion,
                request=request,
                datos_nuevos={"candidatos": cantidad, "lista": participacion_seleccionada.pk},
            )
            messages.success(request, f"Se cargaron {cantidad} personas candidatas.")
        return redirect(
            _url_gestion(
                eleccion.id,
                participacion_id,
                asociacion_seleccionada.id if asociacion_seleccionada else None,
                pestana_candidatos="csv",
            )
        )

    participaciones = eleccion.partidos_participantes.select_related("partido", "eleccion_claustro__claustro").annotate(
        cantidad_listas=Count("listas", distinct=True),
        cantidad_candidatos=Count("listas__candidatos", distinct=True),
    )
    if claustro_seleccionado:
        participaciones = participaciones.filter(eleccion_claustro=claustro_seleccionado)
    claustros = eleccion.elecciones_claustro.select_related("claustro").annotate(
        cantidad_listas=Count("presentaciones_listas", distinct=True),
        cantidad_candidatos=Count("presentaciones_listas__listas__candidatos", distinct=True),
        cantidad_puestos=Count("puestos_electivos", distinct=True),
    )
    puestos = PuestoEleccion.objects.filter(eleccion_claustro__eleccion=eleccion).select_related(
        "puesto__organo", "eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento",
    ).annotate(cantidad_listas=Count("listas_candidatos", distinct=True)).order_by(
        "eleccion_claustro__claustro__nombre",
        "puesto__organo__nombre",
        "puesto__nombre",
        "eleccion_claustro_departamento__departamento__nombre",
    )
    if claustro_seleccionado:
        puestos = puestos.filter(eleccion_claustro=claustro_seleccionado)
    categorias_por_tipo = {
        "departamental": ("Departamentales", 0),
        "directivo": ("Directivos", 1),
        "dasuten": ("DASUTeN", 2),
        "otros": ("Otros puestos", 3),
    }
    opciones_puestos = {
        str(opcion.data["value"]): opcion
        for opcion in formulario_participacion["puestos_eleccion"].subwidgets
    }
    grupos_por_claustro = {}
    puestos_seleccionables = list(
        formulario_participacion.fields["puestos_eleccion"].queryset
    )
    for configuracion in puestos_seleccionables:
        nombre_organo = configuracion.puesto.organo.nombre.casefold()
        if "departamental" in nombre_organo:
            tipo = "departamental"
        elif "directivo" in nombre_organo:
            tipo = "directivo"
        elif "dasuten" in nombre_organo:
            tipo = "dasuten"
        else:
            tipo = "otros"
        claustro_id = configuracion.eleccion_claustro_id
        grupo = grupos_por_claustro.setdefault(
            claustro_id,
            {
                "nombre": str(configuracion.eleccion_claustro.claustro),
                "claustro_id": claustro_id,
                "categorias": {},
            },
        )
        categoria = grupo["categorias"].setdefault(
            tipo,
            {
                "nombre": categorias_por_tipo[tipo][0],
                "orden": categorias_por_tipo[tipo][1],
                "puestos": [],
            },
        )
        opcion = opciones_puestos.get(str(configuracion.pk))
        if opcion is not None:
            categoria["puestos"].append(
                {"configuracion": configuracion, "opcion": opcion}
            )
    puestos_seleccionables_por_claustro = [
        {
            "nombre": grupo["nombre"],
            "claustro_id": grupo["claustro_id"],
            "categorias": sorted(
                grupo["categorias"].values(),
                key=lambda categoria: categoria["orden"],
            ),
        }
        for grupo in grupos_por_claustro.values()
    ]
    return render(
        request,
        "partidos/detalle_participacion.html" if pantalla_candidatos else "partidos/gestion.html",
        {
            "eleccion": eleccion,
            "claustros": claustros,
            "claustro_seleccionado": claustro_seleccionado,
            "pestana": pestana,
            "participaciones": participaciones,
            "formulario_puesto": formulario_puesto,
            "formulario_participacion": formulario_participacion,
            "puestos": puestos,
            "puestos_seleccionables_por_claustro": puestos_seleccionables_por_claustro,
            "participacion_seleccionada": participacion_seleccionada,
            "asociaciones": asociaciones,
            "asociacion_seleccionada": asociacion_seleccionada,
            "pestana_candidatos": pestana_candidatos,
            "formulario_vincular": formulario_vincular,
            "formulario": formulario_vincular,
            "hay_puestos_disponibles_presentacion": formulario_participacion.fields[
                "puestos_eleccion"
            ].queryset.exists(),
            "formulario_candidato": formulario_candidato,
            "candidato_en_edicion": candidato_en_edicion,
            "formulario_csv": formulario_csv,
            "importacion": importacion,
            "hay_puestos_disponibles": formulario_vincular.fields["puesto_eleccion"].queryset.exists()
            if formulario_vincular else False,
        },
    )


@login_required
def descargar_plantilla_candidatos_lista(request, eleccion_id, participacion_id):
    participacion = get_object_or_404(
        ParticipacionPartido.objects.select_related("eleccion"), pk=participacion_id, eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar esta plantilla.")
    lista_id = _id_opcional(request.GET.get("puesto"))
    lista = get_object_or_404(
        ListaCandidatos.objects.select_related(
            "puesto_eleccion__puesto__organo",
            "eleccion_claustro_departamento__departamento",
        ),
        pk=lista_id,
        participacion=participacion,
        activa=True,
        puesto_eleccion__isnull=False,
        puesto_eleccion__activo=True,
    )
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="candidatos-puesto-{lista.pk}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta, delimiter=";")
    escritor.writerow(ENCABEZADOS_CANDIDATOS_LISTA)
    config = lista.puesto_eleccion
    ocupados = set(lista.candidatos.values_list("tipo", "orden"))
    for tipo, cantidad in (
        (Candidato.Tipo.TITULAR, config.cantidad_titulares),
        (Candidato.Tipo.SUPLENTE, config.cantidad_suplentes),
    ):
        for orden in range(1, cantidad + 1):
            if (tipo, orden) not in ocupados:
                escritor.writerow(("DNI", "", tipo, orden))
    return respuesta


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
@require_POST
def cambiar_estado_puesto_eleccion(request, eleccion_id, puesto_id):
    puesto = get_object_or_404(
        PuestoEleccion.objects.select_related("eleccion_claustro__eleccion"),
        pk=puesto_id,
        eleccion_claustro__eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, puesto.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar puestos de esta elección.")
    puesto.activo = request.POST.get("activo") == "1"
    puesto.save(update_fields=("activo",))
    messages.success(request, "El estado del puesto fue actualizado.")
    return redirect(_url_puestos_eleccion(request, eleccion_id))


@login_required
@require_POST
def eliminar_puesto_eleccion(request, eleccion_id, puesto_id):
    puesto = get_object_or_404(
        PuestoEleccion.objects.select_related(
            "eleccion_claustro__eleccion",
            "eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
            "puesto",
        ),
        pk=puesto_id,
        eleccion_claustro__eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, puesto.eleccion):
        return HttpResponseForbidden("No tiene permiso para eliminar puestos de esta elección.")

    datos_anteriores = {
        "claustro": str(puesto.eleccion_claustro.claustro),
        "departamento": str(puesto.eleccion_claustro_departamento.departamento)
        if puesto.eleccion_claustro_departamento_id
        else None,
        "puesto": str(puesto.puesto),
        "cantidad_titulares": puesto.cantidad_titulares,
        "cantidad_suplentes": puesto.cantidad_suplentes,
    }
    try:
        puesto.delete()
    except ProtectedError:
        messages.error(request, "No se puede eliminar el puesto porque está asociado a una o más listas.")
    else:
        registrar_evento(
            accion="eliminar_puesto_eleccion",
            entidad=puesto._meta.label,
            entidad_id=puesto.pk,
            eleccion=puesto.eleccion,
            request=request,
            datos_anteriores=datos_anteriores,
        )
        messages.success(request, "El puesto fue eliminado.")
    return redirect(_url_puestos_eleccion(request, eleccion_id))


def _url_puestos_eleccion(request, eleccion_id):
    url = reverse("gestionar-partidos", args=(eleccion_id,))
    claustro_id = _id_opcional(request.GET.get("claustro"))
    if claustro_id and EleccionClaustro.objects.filter(pk=claustro_id, eleccion_id=eleccion_id).exists():
        return f"{url}?claustro={claustro_id}&pestana=puesto"
    return url


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
    return gestionar_partidos(request, eleccion_id, participacion_id)


@login_required
def editar_participacion(request, eleccion_id, participacion_id):
    participacion = get_object_or_404(
        ParticipacionPartido.objects.select_related("eleccion"),
        pk=participacion_id, eleccion_id=eleccion_id,
    )
    if not _tiene_permiso(request, participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para editar esta lista.")
    formulario = FormularioParticipacionPartido(
        request.POST or None, eleccion=participacion.eleccion, instance=participacion,
    )
    if participacion.listas.exists():
        formulario.fields["eleccion_claustro"].disabled = True
        formulario.fields["eleccion_claustro"].help_text = "El claustro no puede cambiarse porque esta lista ya tiene puestos vinculados."
    if request.method == "POST" and formulario.is_valid():
        guardar_con_validacion(formulario, eleccion=participacion.eleccion)
        messages.success(request, "Los datos de la lista fueron actualizados.")
        return redirect("gestionar-partidos", eleccion_id=eleccion_id)
    return render(request, "partidos/editar_participacion.html", {
        "eleccion": participacion.eleccion,
        "participacion": participacion,
        "formulario": formulario,
    })


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
        return redirect(_url_gestion(eleccion_id, candidato.lista.participacion_id, candidato.lista_id))
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
    return _cambiar_estado(request, participacion, "activa", reverse("gestionar-partidos", args=(eleccion_id,)))


@login_required
def cambiar_estado_lista(request, eleccion_id, lista_id):
    lista = get_object_or_404(ListaCandidatos.objects.select_related("participacion__eleccion"), pk=lista_id, participacion__eleccion_id=eleccion_id)
    if not _tiene_permiso(request, lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar esta lista.")
    return _cambiar_estado(request, lista, "activa", _url_gestion(eleccion_id, lista.participacion_id, lista.id))


@login_required
def cambiar_estado_candidato(request, eleccion_id, candidato_id):
    candidato = get_object_or_404(Candidato.objects.select_related("lista__participacion__eleccion"), pk=candidato_id, lista__participacion__eleccion_id=eleccion_id)
    if not _tiene_permiso(request, candidato.lista.participacion.eleccion):
        return HttpResponseForbidden("No tiene permiso para modificar este candidato.")
    return _cambiar_estado(
        request, candidato, "activo",
        _url_gestion(eleccion_id, candidato.lista.participacion_id, candidato.lista_id),
    )
