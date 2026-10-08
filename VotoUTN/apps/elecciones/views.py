from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    FormularioAlcanceSedes,
    FormularioDepartamentosClaustro,
    FormularioEleccion,
    FormularioEditarEleccion,
    FormularioFechasAdministrativasEleccion,
)
from .models import (
    ESTADOS_ELECCION_NO_CERRADOS,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
)
from apps.autoridades.models import AsignacionAutoridad
from apps.auditoria.services import registrar_evento
from apps.partidos.models import ParticipacionPartido
from apps.padron.models import RegistroPadron
from apps.parametros.models import Claustro
from apps.justificativos.models import JustificativoAusencia
from apps.usuarios.services import elector_de_identidad
from apps.usuarios.permisos import elecciones_con_participacion
from apps.usuarios.permisos import puede_administrar_elecciones, puede_crear_elecciones
from apps.usuarios.models import AsignacionRol


def contexto_formulario_eleccion(formulario, incluir_parametros=False):
    contexto = {
        "campos_generales": [formulario[nombre] for nombre in ("nombre", "fecha_inicio", "fecha_fin")],
    }
    if incluir_parametros:
        contexto["campos_parametros"] = [formulario[nombre] for nombre in ("sedes", "claustros")]
    return contexto


def contexto_fechas_administrativas(formulario):
    return [
        {
            "definicion": definicion,
            "seleccionada": formulario[f"fecha_{definicion.id}_seleccionada"],
            "fecha": formulario[f"fecha_{definicion.id}_valor"],
        }
        for definicion in formulario.definiciones_fechas
    ]


@login_required
def inicio_autenticado(request):
    es_elector = getattr(request.user, "es_elector", False)
    es_autoridad_asignada = False
    if not es_elector:
        roles_persona = AsignacionRol.objects.filter(
            usuario=request.user,
            activo=True,
            rol__in=(AsignacionRol.Rol.ELECTOR, AsignacionRol.Rol.AUTORIDAD_MESA),
        )
        es_elector = roles_persona.filter(rol=AsignacionRol.Rol.ELECTOR).exists()
        es_autoridad_asignada = roles_persona.filter(rol=AsignacionRol.Rol.AUTORIDAD_MESA).exists()
    if es_elector or es_autoridad_asignada:
        elector = elector_de_identidad(request.user)
        registros = RegistroPadron.objects.none()
        if elector is not None:
            registros = RegistroPadron.objects.filter(elector=elector, activo=True).select_related(
                "eleccion",
                "eleccion_claustro_departamento__eleccion_claustro",
                "sede",
                "asignacion_autoridad__mesa__sede",
                "asignacion_autoridad__turno",
            )
        es_autoridad = AsignacionAutoridad.objects.filter(registro_padron__elector=elector).exists() if elector is not None else False
        return render(request, "elecciones/inicio_elector.html", {"registros": registros, "es_autoridad": es_autoridad})
    if AsignacionRol.objects.filter(
        usuario=request.user,
        activo=True,
        rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    ).exists():
        return redirect("inicio-administrador-junta")
    if AsignacionRol.objects.filter(
        usuario=request.user,
        activo=True,
        rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
    ).exists():
        return redirect("inicio-administrativo-junta")
    if puede_administrar_elecciones(request.user):
        return redirect("gestionar-elecciones")
    return redirect("lista-elecciones")


@login_required
def inicio_administrativo_junta(request):
    roles = AsignacionRol.objects.filter(
        usuario=request.user,
        activo=True,
        rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
    )
    if not roles.exists():
        return HttpResponseForbidden("No tiene permiso para acceder al panel administrativo de junta.")
    elecciones = Eleccion.objects.all()
    eleccion_actual = elecciones.order_by("fecha_inicio", "id").first()
    solicitudes_pendientes = JustificativoAusencia.objects.filter(
        registro_padron__eleccion__in=elecciones,
        estado=JustificativoAusencia.Estado.PENDIENTE,
    ).count()
    return render(
        request,
        "gestion/inicio_administrativo_junta.html",
        {
            "eleccion_actual": eleccion_actual,
            "solicitudes_pendientes": solicitudes_pendientes,
        },
    )


@login_required
def inicio_administrador_junta(request):
    roles = AsignacionRol.objects.filter(
        usuario=request.user,
        activo=True,
        rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    ).exclude(eleccion__isnull=True)
    if not roles.exists():
        return HttpResponseForbidden("No tiene permiso para acceder al panel de administrador de junta.")
    elecciones = Eleccion.objects.filter(asignaciones_rol__in=roles).distinct()
    eleccion_actual = elecciones.first()
    solicitudes_pendientes = JustificativoAusencia.objects.filter(
        registro_padron__eleccion__in=elecciones,
        estado=JustificativoAusencia.Estado.PENDIENTE,
    ).count()
    return render(
        request,
        "gestion/inicio_administrador_junta.html",
        {
            "eleccion_actual": eleccion_actual,
            "cantidad_elecciones": elecciones.count(),
            "solicitudes_pendientes": solicitudes_pendientes,
        },
    )


@login_required
def listar_elecciones(request):
    return render(request, "elecciones/list.html", {"elecciones": elecciones_con_participacion(request.user)})

def index(request):
    return render(request, "elecciones/index.html")


@login_required
def gestionar_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar elecciones.")
    estados_gestionables = (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA, Eleccion.Estado.ABIERTA)
    elecciones = Eleccion.objects.filter(estado__in=estados_gestionables)
    return render(request, "elecciones/gestion_lista.html", {"elecciones": elecciones})


@login_required
def historial_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para consultar el historial.")
    elecciones = Eleccion.objects.filter(estado=Eleccion.Estado.CERRADA)
    return render(request, "elecciones/historial_elecciones.html", {"elecciones": elecciones})


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
            "cantidad_partidos": ParticipacionPartido.objects.filter(eleccion=eleccion, activa=True).count(),
            "cantidad_fechas_administrativas": eleccion.fechas_administrativas.count(),
        },
    )


@login_required
def gestionar_fechas_administrativas(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para configurar esta eleccion.")
    formulario_fechas = FormularioFechasAdministrativasEleccion(
        request.POST or None,
        eleccion=eleccion,
    )
    if request.method == "POST" and formulario_fechas.is_valid():
        formulario_fechas.guardar()
        messages.success(request, "Las fechas administrativas fueron actualizadas.")
        return redirect("gestionar-fechas-administrativas", eleccion_id=eleccion.id)
    return render(
        request,
        "elecciones/fechas_administrativas.html",
        {
            "eleccion": eleccion,
            "formulario_fechas": formulario_fechas,
            "fechas_administrativas": contexto_fechas_administrativas(formulario_fechas),
        },
    )


@login_required
def crear_eleccion(request):
    if not puede_crear_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para crear elecciones.")

    eleccion_existente = Eleccion.objects.filter(estado__in=ESTADOS_ELECCION_NO_CERRADOS).first()
    if eleccion_existente:
        return render(
            request,
            "elecciones/formulario_eleccion.html",
            {"eleccion_existente": eleccion_existente},
        )

    formulario = FormularioEleccion(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        with transaction.atomic():
            eleccion = formulario.save()
            if AsignacionRol.objects.filter(
                usuario=request.user,
                activo=True,
                rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            ).exists():
                AsignacionRol.objects.get_or_create(
                    usuario=request.user,
                    rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
                    eleccion=eleccion,
                    defaults={"activo": True},
                )
        messages.success(request, "La eleccion fue creada y quedo configurada.")
        return redirect("configurar-eleccion", eleccion_id=eleccion.id)
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
    return redirect("previsualizar-padron", eleccion_id=eleccion_id, claustro_id=claustro_id)



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
            "claustros": eleccion.elecciones_claustro.select_related("claustro").prefetch_related(
                "sedes_habilitadas__sede",
                "departamentos__departamento",
                "departamentos__sedes_habilitadas__sede",
            ),
        },
    )


@login_required
def gestionar_departamentos_claustro(request, eleccion_id, claustro_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")
    if eleccion.estado in (Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
        return HttpResponseForbidden("No se pueden modificar alcances en una eleccion abierta o cerrada.")
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("claustro"),
        pk=claustro_id,
        eleccion=eleccion,
    )
    if (
        eleccion_claustro.organizacion_departamentos
        == Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO
    ):
        return HttpResponseForbidden("Este claustro no se organiza por departamentos.")

    formulario = FormularioDepartamentosClaustro(
        request.POST if request.method == "POST" else None,
        eleccion_claustro=eleccion_claustro,
    )
    if request.method == "POST" and formulario.is_valid():
        formulario.guardar()
        messages.success(request, "Los departamentos habilitados fueron actualizados.")
        return redirect("gestionar-alcances", eleccion_id=eleccion.id)
    return render(
        request,
        "elecciones/editar_departamentos.html",
        {
            "eleccion": eleccion,
            "eleccion_claustro": eleccion_claustro,
            "formulario": formulario,
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
        titulo = f"Sedes de {objeto.nombre_alcance}"
    else:
        raise Http404()
    formulario = FormularioAlcanceSedes(request.POST or None, eleccion=eleccion, objeto=objeto, tipo=tipo)
    if request.method == "POST" and formulario.is_valid():
        formulario.guardar()
        messages.success(request, "Las sedes habilitadas fueron actualizadas.")
        return redirect("gestionar-alcances", eleccion_id=eleccion.id)
    return render(request, "elecciones/editar_alcance.html", {"eleccion": eleccion, "titulo": titulo, "formulario": formulario})
