from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    FormularioAlcanceSedes,
    FormularioEleccion,
    FormularioEditarEleccion,
    FormularioPrepararClaustro,
)
from .models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.autoridades.models import AsignacionAutoridad
from apps.auditoria.services import registrar_evento
from apps.usuarios.permisos import elecciones_con_participacion
from apps.usuarios.permisos import puede_administrar_elecciones
from apps.usuarios.models import AsignacionRol


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


@login_required
def listar_elecciones(request):
    return render(request, "elecciones/list.html", {"elecciones": elecciones_con_participacion(request.user)})

def index(request):
    return render(request, "elecciones/index.html")


@login_required
def gestionar_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar elecciones.")
    return render(request, "elecciones/gestion_lista.html", {"elecciones": Eleccion.objects.all()})


@login_required
def historial_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para consultar el historial.")
    return render(request, "elecciones/historial_elecciones.html", {"elecciones": Eleccion.objects.all()})


@login_required
def configurar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para configurar esta eleccion.")
    return render(
        request,
        "elecciones/configurar_eleccion.html",
        {
            "eleccion": eleccion,
            "cantidad_padrones": eleccion.registros_padron.count(),
            "cantidad_mesas": eleccion.mesas.count(),
            "cantidad_autoridades": AsignacionAutoridad.objects.filter(mesa__eleccion=eleccion).count(),
        },
    )


@login_required
def crear_eleccion(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para crear elecciones.")

    formulario = FormularioEleccion(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        eleccion = formulario.save()
        messages.success(request, "La eleccion fue creada y quedo configurada.")
        return redirect("preparar-eleccion", eleccion_id=eleccion.id)
    return render(request, "elecciones/formulario_eleccion.html", {"formulario": formulario, **contexto_formulario_eleccion(formulario, incluir_parametros=True)})


@login_required
def preparar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para preparar esta eleccion.")
    claustros = eleccion.elecciones_claustro.select_related("claustro").prefetch_related("departamentos__departamento", "sedes_habilitadas__sede")
    return render(request, "elecciones/preparar_eleccion.html", {"eleccion": eleccion, "claustros": claustros})


@login_required
def preparar_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para preparar este claustro.")
    formulario = FormularioPrepararClaustro(request.POST or None, instance=eleccion_claustro)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "La configuracion del claustro fue guardada.")
        return redirect("preparar-eleccion", eleccion_id=eleccion_id)
    return render(request, "elecciones/preparar_claustro.html", {"eleccion": eleccion_claustro.eleccion, "claustro": eleccion_claustro, "formulario": formulario})



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
    estado_anterior = eleccion.estado
    try:
        eleccion.cambiar_estado(nuevo_estado)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        registrar_evento(
            accion="eleccion.cambio_estado",
            entidad="Eleccion",
            entidad_id=eleccion.id,
            eleccion=eleccion,
            usuario=request.user,
            request=request,
            datos_anteriores={"estado": estado_anterior},
            datos_nuevos={"estado": eleccion.estado, "habilitada": eleccion.habilitada},
        )
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
