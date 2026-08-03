from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    FormularioAlcanceSedes,
    FormularioClaustro,
    FormularioDepartamento,
    FormularioEleccion,
    FormularioEditarEleccion,
    FormularioFechaAdministrativa,
    FormularioGenerarMesas,
    FormularioSede,
    FormularioTurno,
    preparar_formulario_parametro,
)
from .models import Claustro, Departamento, Eleccion, EleccionClaustro, EleccionClaustroDepartamento, FechaAdministrativa, Sede, Turno
from apps.usuarios.permisos import elecciones_con_participacion
from apps.usuarios.permisos import puede_administrar_elecciones, puede_administrar_parametros


PARAMETROS = {
    "sedes": {"modelo": Sede, "formulario": FormularioSede, "titulo": "Sedes", "estado": "activa", "codigo": True},
    "claustros": {"modelo": Claustro, "formulario": FormularioClaustro, "titulo": "Claustros", "estado": "activo", "codigo": True},
    "departamentos": {"modelo": Departamento, "formulario": FormularioDepartamento, "titulo": "Departamentos", "estado": "activo", "codigo": True},
    "turnos": {"modelo": Turno, "formulario": FormularioTurno, "titulo": "Turnos", "estado": "activo", "codigo": False},
    "fechas-administrativas": {"modelo": FechaAdministrativa, "formulario": FormularioFechaAdministrativa, "titulo": "Fechas administrativas", "estado": "activa", "codigo": False, "es_fecha": True},
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
    return render(request, "elecciones/gestion_lista.html", {"elecciones": Eleccion.objects.exclude(estado=Eleccion.Estado.CERRADA)})


@login_required
def historial_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para consultar el historial.")
    return render(request, "elecciones/historial_elecciones.html", {"elecciones": Eleccion.objects.filter(estado=Eleccion.Estado.CERRADA)})


@login_required
def crear_eleccion(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para crear elecciones.")

    formulario = FormularioEleccion(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        eleccion = formulario.save()
        messages.success(request, "La eleccion fue creada y quedo configurada.")
        return redirect("gestionar-elecciones")
    return render(request, "elecciones/formulario_eleccion.html", {"formulario": formulario, **contexto_formulario_eleccion(formulario, incluir_parametros=True)})


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

    if eleccion.estado not in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA):
        return HttpResponseForbidden("No se pueden generar mesas en una eleccion abierta o cerrada.")
    formulario = FormularioGenerarMesas(request.POST or None, eleccion=eleccion)
    if request.method == "POST" and formulario.is_valid():
        mesas = formulario.generar()
        messages.success(request, f"Se generaron {len(mesas)} mesas.")
        return redirect("gestionar-mesas", eleccion_id=eleccion.id)
    return render(
        request,
        "elecciones/gestion_mesas.html",
        {"eleccion": eleccion, "formulario": formulario, "mesas": eleccion.mesas.select_related("sede", "turno", "eleccion_claustro_departamento__eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento")},
    )
