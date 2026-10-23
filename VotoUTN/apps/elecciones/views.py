from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    FormularioAgregarClaustro,
    FormularioAlcanceSedes,
    FormularioDepartamentosClaustro,
    FormularioEleccion,
    FormularioEditarEleccion,
    FormularioFechasAdministrativasEleccion,
)
from .services import agregar_claustro, eliminar_claustro
from .models import (
    ESTADOS_ELECCION_NO_CERRADOS,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
)
from apps.asistencia.dashboard import (
    FiltrosDashboard,
    construir_dashboard,
    opciones_filtros,
    seleccionar_eleccion_actual,
)
from apps.autoridades.models import AsignacionAutoridad
from apps.auditoria.services import registrar_evento
from apps.mesas.models import Mesa
from apps.partidos.models import ParticipacionPartido
from apps.padron.models import RegistroPadron, SolicitudCambioSede
from apps.parametros.models import Claustro
from apps.padron.services import rehabilitar_cambios_padron as servicio_rehabilitar_cambios_padron
from apps.justificativos.models import JustificativoAusencia
from apps.notificaciones.services import (
    crear_notificaciones_ausentes_confirmadas,
    enviar_notificacion,
    notificar_eleccion_en_curso,
    notificar_eleccion_publicada,
)
from apps.usuarios.services import elector_de_identidad
from apps.usuarios.permisos import (
    elecciones_con_participacion,
    puede_administrar_elecciones,
    puede_configurar_eleccion,
    puede_crear_elecciones,
)
from apps.usuarios.models import AsignacionRol

MESAS_POR_PAGINA = 10


def contexto_formulario_eleccion(formulario, incluir_parametros=False):
    contexto = {
        "campos_generales": [
            formulario[nombre]
            for nombre in ("nombre", "fecha_inicio", "fecha_fin", "fecha_cierre_solicitudes_cambio_sede")
        ],
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
                "asignacion_autoridad__mesa__eleccion_claustro_departamento__departamento",
                "asignacion_autoridad__turno",
                "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento",
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
        return redirect("inicio-administrador-junta")
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
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para acceder al panel de administrador de junta.")
    elecciones = Eleccion.objects.all()
    eleccion_actual = elecciones.filter(estado__in=ESTADOS_ELECCION_NO_CERRADOS).order_by("-fecha_inicio", "-id").first()
    solicitudes_pendientes = JustificativoAusencia.objects.filter(
        registro_padron__eleccion=eleccion_actual,
        estado=JustificativoAusencia.Estado.PENDIENTE,
    ).count()
    cambios_pendientes = SolicitudCambioSede.objects.filter(
        registro_padron__eleccion=eleccion_actual,
        estado=SolicitudCambioSede.Estado.PENDIENTE,
    ).count()
    dashboard = construir_dashboard(request.user, eleccion_actual, FiltrosDashboard()) if eleccion_actual else None
    return render(
        request,
        "gestion/inicio_administrador_junta.html",
        {
            "eleccion_actual": eleccion_actual,
            "cantidad_elecciones": elecciones.count(),
            "solicitudes_pendientes": solicitudes_pendientes,
            "cambios_pendientes": cambios_pendientes,
            "dashboard": dashboard,
        },
    )


@login_required
def listar_elecciones(request):
    elecciones = elecciones_con_participacion(request.user)
    hay_eleccion_en_curso = Eleccion.objects.filter(
        estado=Eleccion.Estado.ABIERTA,
    ).exists()
    contexto = {
        "elecciones": elecciones,
        "hay_eleccion_en_curso": hay_eleccion_en_curso,
    }
    eleccion_actual = seleccionar_eleccion_actual(elecciones, request.GET.get("eleccion"))
    if hay_eleccion_en_curso and eleccion_actual is not None:
        filtros = FiltrosDashboard.desde_parametros(request.GET)
        dashboard = construir_dashboard(request.user, eleccion_actual, filtros)
        parametros = request.GET.copy()
        parametros.pop("pagina", None)
        contexto.update(
            eleccion_actual=eleccion_actual,
            filtros=filtros,
            opciones_filtros=opciones_filtros(eleccion_actual),
            dashboard=dashboard,
            pagina_mesas=Paginator(dashboard["mesas"], MESAS_POR_PAGINA).get_page(request.GET.get("pagina")),
            querystring_paginacion=parametros.urlencode(),
        )
        puede_confirmar_ausentes = (
            puede_administrar_elecciones(request.user, eleccion_actual)
            and eleccion_actual.estado == Eleccion.Estado.ABIERTA
            and eleccion_actual.notificaciones_ausentes_confirmadas_en is None
            and eleccion_actual.mesas.exists()
            and not eleccion_actual.mesas.exclude(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA).exists()
        )
        contexto["puede_confirmar_notificaciones_ausentes"] = puede_confirmar_ausentes
    return render(request, "elecciones/list.html", contexto)


@login_required
def confirmar_notificaciones_ausentes(request, eleccion_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("Solo el administrador de junta puede confirmar las notificaciones a ausentes.")
    try:
        envios = crear_notificaciones_ausentes_confirmadas(eleccion)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect(f"{reverse('lista-elecciones')}?eleccion={eleccion.pk}")

    enviados = sum(enviar_notificacion(envio) for envio in envios)
    registrar_evento(
        accion="eleccion.notificaciones_ausentes_confirmadas",
        entidad="Eleccion",
        entidad_id=eleccion.pk,
        eleccion=eleccion,
        usuario=request.user,
        request=request,
        datos_nuevos={
            "notificaciones_creadas": len(envios),
            "correos_enviados": enviados,
            "correos_no_enviados": len(envios) - enviados,
        },
    )
    if not envios:
        messages.success(request, "Escaneo confirmado: no se registraron ausentes para notificar.")
    elif enviados == len(envios):
        messages.success(request, f"Se notificó a {len(envios)} electores ausentes por correo y en la aplicación.")
    else:
        messages.warning(
            request,
            f"Se generaron notificaciones para {len(envios)} ausentes. "
            f"Correos enviados: {enviados}; con error: {len(envios) - enviados}. "
            "Las notificaciones permanecen disponibles en la aplicación.",
        )
    return redirect(f"{reverse('lista-elecciones')}?eleccion={eleccion.pk}")


def index(request):
    return render(request, "elecciones/index.html")


@login_required
def gestionar_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar elecciones.")
    estados_gestionables = (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA, Eleccion.Estado.ABIERTA)
    elecciones = Eleccion.objects.filter(estado__in=estados_gestionables)
    if elecciones.exists():
        return configurar_eleccion(request, elecciones.first().pk)
    return render(
        request,
        "elecciones/gestion_lista.html",
        {"elecciones": elecciones, "eleccion_en_curso": elecciones.first()},
    )


@login_required
def historial_elecciones(request):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para consultar el historial.")
    elecciones = Eleccion.objects.filter(estado=Eleccion.Estado.CERRADA)
    return render(request, "elecciones/historial_elecciones.html", {"elecciones": elecciones})


@login_required
def dashboard_historial_eleccion(request, eleccion_id):
    if not puede_administrar_elecciones(request.user):
        return HttpResponseForbidden("No tiene permiso para consultar el historial.")
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id, estado=Eleccion.Estado.CERRADA)
    filtros = FiltrosDashboard.desde_parametros(request.GET)
    dashboard = construir_dashboard(request.user, eleccion, filtros)
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return render(
        request,
        "elecciones/dashboard_historial.html",
        {
            "modo_historial": True,
            "eleccion_actual": eleccion,
            "filtros": filtros,
            "opciones_filtros": opciones_filtros(eleccion),
            "dashboard": dashboard,
            "pagina_mesas": Paginator(dashboard["mesas"], MESAS_POR_PAGINA).get_page(request.GET.get("pagina")),
            "querystring_paginacion": parametros.urlencode(),
        },
    )


@login_required
def configurar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=True):
        return HttpResponseForbidden("No tiene permiso para configurar esta eleccion.")
    pendientes_configuracion = []
    try:
        eleccion.validar_configuracion()
    except ValidationError as error:
        pendientes_configuracion = error.messages
    estados = [
        (Eleccion.Estado.BORRADOR, "Se configuran sedes, claustros, padrones, mesas y autoridades."),
        (Eleccion.Estado.PREPARADA, "Se reciben cambios de sede y justificativos. No se agregan claustros."),
        (Eleccion.Estado.ABIERTA, "Se registra participación y se emite el padrón. La configuración queda en lectura."),
        (Eleccion.Estado.CERRADA, "Consulta histórica. La configuración y las resoluciones quedan bloqueadas."),
    ]
    siguiente_estado = {
        Eleccion.Estado.BORRADOR: (Eleccion.Estado.PREPARADA, "Publicar elección"),
        Eleccion.Estado.PREPARADA: (Eleccion.Estado.ABIERTA, "Iniciar elección"),
        Eleccion.Estado.ABIERTA: (Eleccion.Estado.CERRADA, "Finalizar elección"),
    }.get(eleccion.estado)
    claustros = eleccion.elecciones_claustro.all()
    alcances_pendientes = (
        not eleccion.elecciones_sede.exists()
        or not claustros.exists()
        or claustros.filter(Q(sedes_habilitadas__isnull=True) | Q(departamentos__isnull=True)).exists()
        or EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion, sedes_habilitadas__isnull=True,
        ).exists()
    )
    padrones_pendientes = (
        not claustros.exists()
        or claustros.exclude(departamentos__registros_padron__activo=True).exists()
        or claustros.filter(Q(fecha_votacion__isnull=True) | Q(maximo_votantes_por_mesa__isnull=True)).exists()
    )
    autoridades_pendientes = eleccion.mesas.filter(autoridades__isnull=True).exists() or not eleccion.mesas.exists()
    return render(
        request,
        "elecciones/configurar_eleccion.html",
        {
            "eleccion": eleccion,
            "linea_tiempo": [
                {"codigo": codigo, "nombre": Eleccion.Estado(codigo).label, "ayuda": ayuda}
                for codigo, ayuda in estados
            ],
            "siguiente_estado": siguiente_estado,
            "pendientes_configuracion": pendientes_configuracion,
            "padrones_pendientes": padrones_pendientes,
            "alcances_pendientes": alcances_pendientes,
            "autoridades_pendientes": autoridades_pendientes,
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
    if not puede_administrar_elecciones(request.user, eleccion) or eleccion.estado == Eleccion.Estado.CERRADA:
        return HttpResponseForbidden("No tiene permiso para configurar esta eleccion.")
    formulario_fechas = FormularioFechasAdministrativasEleccion(
        request.POST if request.method == "POST" else None,
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
        messages.success(request, "La elección fue creada. Completá las sedes y departamentos de sus claustros antes de continuar.")
        return redirect("gestionar-alcances", eleccion_id=eleccion.id)
    return render(request, "elecciones/formulario_eleccion.html", {"formulario": formulario, **contexto_formulario_eleccion(formulario, incluir_parametros=True)})


@login_required
def preparar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=True):
        return HttpResponseForbidden("No tiene permiso para preparar esta eleccion.")
    claustros = eleccion.elecciones_claustro.select_related("claustro").prefetch_related(
        "departamentos__departamento",
        "sedes_habilitadas__sede",
    ).annotate(
        cantidad_electores=Count(
            "departamentos__registros_padron",
            filter=Q(departamentos__registros_padron__activo=True),
            distinct=True,
        )
    )
    return render(request, "elecciones/preparar_eleccion.html", {"eleccion": eleccion, "claustros": claustros})


@login_required
def preparar_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion_claustro.eleccion, solo_consulta=True):
        return HttpResponseForbidden("No tiene permiso para preparar este claustro.")
    return redirect("previsualizar-padron", eleccion_id=eleccion_id, claustro_id=claustro_id)


@login_required
def rehabilitar_cambios_padron(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(EleccionClaustro, pk=claustro_id, eleccion_id=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion_claustro.eleccion):
        return HttpResponseForbidden("No tiene permiso para rehabilitar cambios de padrón.")
    if request.method == "POST":
        servicio_rehabilitar_cambios_padron(eleccion_claustro, request.user)
        messages.success(request, "La emisión anterior fue invalidada. Podés modificar la configuración, recalcular mesas y emitir un padrón imprimible nuevo.")
        return redirect("previsualizar-padron", eleccion_id=eleccion_id, claustro_id=claustro_id)
    return render(request, "elecciones/rehabilitar_cambios_padron.html", {"eleccion": eleccion_claustro.eleccion, "claustro": eleccion_claustro})



@login_required
def editar_eleccion(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para editar esta eleccion.")
    if request.method == "POST" and eleccion.estado in (Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
        return HttpResponseForbidden("No se puede editar una eleccion abierta o cerrada.")
    formulario = FormularioEditarEleccion(request.POST or None, instance=eleccion)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "Los datos de la eleccion fueron actualizados.")
        return redirect("gestionar-elecciones")
    return render(request, "elecciones/editar_eleccion.html", {"eleccion": eleccion, "formulario": formulario, **contexto_formulario_eleccion(formulario)})


ETIQUETA_POPUP_TRANSICION = "popup transicion-bloqueada"


@login_required
def cambiar_estado_eleccion(request, eleccion_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion) or eleccion.estado == Eleccion.Estado.CERRADA:
        return HttpResponseForbidden("No tiene permiso para cambiar esta eleccion.")
    nuevo_estado = request.POST.get("estado")
    estado_anterior = eleccion.estado
    if nuevo_estado == Eleccion.Estado.CERRADA:
        hay_justificativos_pendientes = JustificativoAusencia.objects.filter(
            registro_padron__eleccion=eleccion,
            estado=JustificativoAusencia.Estado.PENDIENTE,
        ).exists()
        if hay_justificativos_pendientes:
            messages.error(request, "No se puede finalizar la elección con justificativos pendientes.", extra_tags=ETIQUETA_POPUP_TRANSICION)
            return redirect("gestionar-elecciones")
        hay_mesas_pendientes = Mesa.objects.filter(
            eleccion=eleccion,
            estado_escaneo__in=(Mesa.EstadoEscaneo.PENDIENTE, Mesa.EstadoEscaneo.EN_PROCESO),
        ).exists()
        if hay_mesas_pendientes:
            messages.error(request, "No se puede finalizar la elección con mesas pendientes de escaneo.", extra_tags=ETIQUETA_POPUP_TRANSICION)
            return redirect("gestionar-elecciones")
    try:
        eleccion.cambiar_estado(nuevo_estado)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages), extra_tags=ETIQUETA_POPUP_TRANSICION)
    else:
        if nuevo_estado == Eleccion.Estado.PREPARADA:
            notificar_eleccion_publicada(eleccion)
        elif nuevo_estado == Eleccion.Estado.ABIERTA:
            notificar_eleccion_en_curso(eleccion)
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
        messages.success(request, f"La elección quedó {eleccion.get_estado_display().lower()}.")
    return redirect("gestionar-elecciones")


@login_required
def gestionar_alcances(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")
    formulario = FormularioAgregarClaustro(
        request.POST if request.method == "POST" and request.POST.get("accion") == "agregar_claustro" else None,
        eleccion=eleccion,
    )
    if request.method == "POST":
        if eleccion.estado != Eleccion.Estado.BORRADOR:
            return HttpResponseForbidden("Solo se pueden agregar o eliminar claustros en estado En preparación.")
        accion = request.POST.get("accion")
        if accion == "agregar_claustro" and formulario.is_valid():
            try:
                agregar_claustro(eleccion, formulario.cleaned_data["claustro"])
            except ValueError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, "El claustro fue agregado y heredó las sedes de la elección.")
            return redirect("gestionar-alcances", eleccion_id=eleccion.pk)
        if accion == "eliminar_claustro":
            configuracion = get_object_or_404(EleccionClaustro, pk=request.POST.get("claustro_id"), eleccion=eleccion)
            try:
                eliminar_claustro(configuracion, request.user)
            except ValueError as error:
                messages.error(request, str(error))
            else:
                messages.success(request, "El claustro fue eliminado de la elección.")
            return redirect("gestionar-alcances", eleccion_id=eleccion.pk)
        if accion not in ("agregar_claustro", "eliminar_claustro"):
            messages.error(request, "La acción solicitada no es válida.")
    return render(
        request,
        "elecciones/alcances.html",
        {
            "eleccion": eleccion,
            "formulario_agregar_claustro": formulario,
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
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")
    if request.method == "POST" and eleccion.estado in (Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
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
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")
    if request.method == "POST" and eleccion.estado in (Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
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
