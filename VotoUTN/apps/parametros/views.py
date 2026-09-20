from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.auditoria.services import registrar_evento
from apps.justificativos.models import TipoJustificativo
from apps.notificaciones.forms import (
    FormularioComunicacionFechaAdministrativa,
    FormularioPlantillaNotificacion,
    FormularioVarianteComunicacion,
)
from apps.notificaciones.models import (
    ComunicacionFechaAdministrativa,
    PlantillaNotificacion,
    VarianteComunicacionFechaAdministrativa,
)
from apps.partidos.forms import FormularioCargoElectivo, FormularioOrganoElectivo
from apps.partidos.models import CargoElectivo, OrganoElectivo
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno
from apps.parametros.forms import (
    FormularioClaustro,
    FormularioDepartamento,
    FormularioFechaAdministrativa,
    FormularioSede,
    FormularioTipoJustificativo,
    FormularioTurno,
    preparar_formulario_parametro,
)
from apps.usuarios.permisos import puede_administrar_parametros


PARAMETROS = {
    "sedes": {"modelo": Sede, "formulario": FormularioSede, "titulo": "Sedes", "estado": "activa", "codigo": False},
    "claustros": {"modelo": Claustro, "formulario": FormularioClaustro, "titulo": "Claustros", "estado": "activo", "codigo": False},
    "departamentos": {"modelo": Departamento, "formulario": FormularioDepartamento, "titulo": "Departamentos", "estado": "activo", "codigo": True},
    "turnos": {"modelo": Turno, "formulario": FormularioTurno, "titulo": "Turnos", "estado": "activo", "codigo": False, "es_turno": True},
    "fechas-administrativas": {"modelo": FechaAdministrativa, "formulario": FormularioFechaAdministrativa, "titulo": "Fechas administrativas", "estado": "activa", "codigo": True, "es_fecha": True},
    "tipos-justificativo": {"modelo": TipoJustificativo, "formulario": FormularioTipoJustificativo, "titulo": "Tipos de justificativo", "estado": "activo", "codigo": False},
    "plantillas-mensajes": {"modelo": PlantillaNotificacion, "formulario": FormularioPlantillaNotificacion, "titulo": "Plantillas de mensajes", "estado": "activa", "codigo": True, "es_plantilla": True},
    "organos-electivos": {"modelo": OrganoElectivo, "formulario": FormularioOrganoElectivo, "titulo": "Órganos o cuerpos", "estado": "activo", "codigo": False, "grupo": "puestos"},
    "puestos-electivos": {"modelo": CargoElectivo, "formulario": FormularioCargoElectivo, "titulo": "Puestos a elegir", "estado": "activo", "codigo": False, "grupo": "puestos", "es_cargo": True},
}


def _datos_auditables(objeto):
    return {
        campo.name: str(getattr(objeto, campo.name))
        for campo in objeto._meta.fields
        if campo.name not in {"id"}
    }


def obtener_parametro(tipo):
    try:
        return PARAMETROS[tipo]
    except KeyError as error:
        raise Http404("Tipo de parametro inexistente.") from error


@login_required
def gestionar_parametros(request):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    parametros = [
        {"tipo": tipo, "titulo": configuracion["titulo"], "cantidad": configuracion["modelo"].objects.count()}
        for tipo, configuracion in PARAMETROS.items()
        if not configuracion.get("grupo")
    ]
    parametros.append({
        "titulo": "Puestos a elegir",
        "es_grupo_candidaturas": True,
        "resumen": (
            f"{CargoElectivo.objects.count()} puestos registrados en "
            f"{OrganoElectivo.objects.count()} órganos o cuerpos."
        ),
    })
    return render(request, "parametros/gestion.html", {"parametros": parametros})


@login_required
def gestionar_catalogos_candidaturas(request):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    catalogos = [
        {"tipo": tipo, "titulo": PARAMETROS[tipo]["titulo"], "cantidad": PARAMETROS[tipo]["modelo"].objects.count()}
        for tipo in ("organos-electivos", "puestos-electivos")
    ]
    return render(request, "parametros/candidaturas.html", {"catalogos": catalogos})


@login_required
def listar_parametros(request, tipo):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    configuracion = obtener_parametro(tipo)
    consulta = request.GET.get("q", "").strip()
    objetos = configuracion["modelo"].objects.all()
    if configuracion.get("es_cargo"):
        objetos = objetos.select_related("organo")
    if consulta:
        filtro = Q(nombre__icontains=consulta)
        if configuracion["codigo"]:
            filtro |= Q(codigo__icontains=consulta)
        if configuracion.get("es_cargo"):
            filtro |= Q(organo__nombre__icontains=consulta)
        objetos = objetos.filter(filtro)
    return render(
        request,
        "parametros/lista.html",
        {
            "tipo": tipo, "titulo": configuracion["titulo"], "objetos": objetos,
            "consulta": consulta, "campo_estado": configuracion["estado"],
            "tiene_codigo": configuracion["codigo"], "es_fecha": configuracion.get("es_fecha", False),
            "es_plantilla": configuracion.get("es_plantilla", False), "es_turno": configuracion.get("es_turno", False),
            "es_cargo": configuracion.get("es_cargo", False),
            "es_catalogo_candidaturas": configuracion.get("grupo") == "puestos",
        },
    )


@login_required
def editar_parametro(request, tipo, objeto_id=None):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    configuracion = obtener_parametro(tipo)
    objeto = get_object_or_404(configuracion["modelo"], pk=objeto_id) if objeto_id else None
    datos_anteriores = _datos_auditables(objeto) if objeto else {}
    formulario = preparar_formulario_parametro(configuracion["formulario"](request.POST or None, instance=objeto))
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.save()
        registrar_evento(
            accion="actualizar_parametro" if objeto else "crear_parametro",
            entidad=guardado._meta.label,
            entidad_id=guardado.pk,
            request=request,
            datos_anteriores=datos_anteriores,
            datos_nuevos=_datos_auditables(guardado),
        )
        messages.success(request, f"{configuracion['titulo'][:-1]} guardado correctamente.")
        return redirect("listar-parametros", tipo=tipo)
    return render(
        request,
        "parametros/formulario.html",
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
    datos_anteriores = _datos_auditables(objeto)
    setattr(objeto, campo_estado, not getattr(objeto, campo_estado))
    objeto.save(update_fields=(campo_estado,))
    registrar_evento(
        accion="cambiar_estado_parametro",
        entidad=objeto._meta.label,
        entidad_id=objeto.pk,
        request=request,
        datos_anteriores=datos_anteriores,
        datos_nuevos=_datos_auditables(objeto),
    )
    messages.success(request, "El estado fue actualizado.")
    return redirect("listar-parametros", tipo=tipo)


@login_required
def gestionar_comunicaciones_fecha(request, fecha_id):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    fecha = get_object_or_404(FechaAdministrativa, pk=fecha_id)
    return render(
        request,
        "parametros/comunicaciones.html",
        {"fecha": fecha, "comunicaciones": fecha.comunicaciones.prefetch_related("variantes__plantilla")},
    )


@login_required
def editar_comunicacion_fecha(request, fecha_id, comunicacion_id=None):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    fecha = get_object_or_404(FechaAdministrativa, pk=fecha_id)
    comunicacion = (
        get_object_or_404(fecha.comunicaciones, pk=comunicacion_id)
        if comunicacion_id
        else ComunicacionFechaAdministrativa(fecha_administrativa=fecha)
    )
    formulario = preparar_formulario_parametro(FormularioComunicacionFechaAdministrativa(request.POST or None, instance=comunicacion))
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.save(commit=False)
        guardado.fecha_administrativa = fecha
        guardado.save()
        registrar_evento(accion="guardar_comunicacion_fecha", entidad=guardado._meta.label, entidad_id=guardado.pk, request=request, datos_nuevos=_datos_auditables(guardado))
        messages.success(request, "La comunicación sugerida fue guardada.")
        return redirect("comunicaciones-fecha", fecha_id=fecha.pk)
    return render(request, "parametros/formulario_relacionado.html", {"titulo": "Comunicación sugerida", "formulario": formulario, "volver_id": fecha.pk})


@login_required
def editar_variante_comunicacion(request, comunicacion_id, variante_id=None):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    comunicacion = get_object_or_404(ComunicacionFechaAdministrativa.objects.select_related("fecha_administrativa"), pk=comunicacion_id)
    variante = (
        get_object_or_404(comunicacion.variantes, pk=variante_id)
        if variante_id
        else VarianteComunicacionFechaAdministrativa(comunicacion=comunicacion)
    )
    formulario = preparar_formulario_parametro(FormularioVarianteComunicacion(request.POST or None, instance=variante))
    if request.method == "POST" and formulario.is_valid():
        guardado = formulario.save(commit=False)
        guardado.comunicacion = comunicacion
        guardado.save()
        registrar_evento(accion="guardar_variante_comunicacion", entidad=guardado._meta.label, entidad_id=guardado.pk, request=request, datos_nuevos=_datos_auditables(guardado))
        messages.success(request, "La variante fue guardada.")
        return redirect("comunicaciones-fecha", fecha_id=comunicacion.fecha_administrativa_id)
    return render(request, "parametros/formulario_relacionado.html", {"titulo": "Variante de mensaje", "formulario": formulario, "volver_id": comunicacion.fecha_administrativa_id})


@login_required
def previsualizar_plantilla(request, plantilla_id):
    if not puede_administrar_parametros(request.user):
        return HttpResponseForbidden("No tiene permiso para gestionar parametros.")
    plantilla = get_object_or_404(PlantillaNotificacion, pk=plantilla_id)
    ejemplos = {
        "nombre_destinatario": "María Pérez", "nombre_eleccion": "Elección UTN",
        "nombre_fecha_administrativa": "Fecha administrativa", "fecha_inicio": "01/10/2026",
        "fecha_fin": "30/10/2026", "claustros": "Docentes", "mesa": "12", "sede": "Medrano",
        "turno": "Mañana", "horario_turno": "08:00 a 13:00", "fecha_votacion": "15/11/2026",
        "url_accion": "https://voto.utn.edu.ar/gestion", "fecha_capacitacion": "10/11/2026",
        "hora_capacitacion": "18:00", "lugar_capacitacion": "Aula Magna", "fecha_presentacion": "02/10/2026 10:30",
        "estado_solicitud": "Pendiente", "observacion_resolucion": "Documentación validada.",
        "sede_solicitada": "Campus", "turno_solicitado": "Tarde",
    }
    asunto, contenido = plantilla.asunto, plantilla.contenido
    for variable, valor in ejemplos.items():
        asunto = asunto.replace("{" + variable + "}", valor)
        contenido = contenido.replace("{" + variable + "}", valor)
    return render(request, "parametros/previsualizar_plantilla.html", {"plantilla": plantilla, "asunto": asunto, "contenido": contenido})
