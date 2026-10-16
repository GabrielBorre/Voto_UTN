import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.autoridades.forms import (
    FormularioArchivoAutoridades,
    FormularioBusquedaCandidato,
    FormularioPreferenciaAutoridad,
    FormularioTurnosAutoridades,
)
from apps.autoridades.services import (
    PLANTILLA_AUTORIDADES_EJEMPLO,
    PLANTILLA_AUTORIDADES_HEADERS,
    confirmar_cambio_sede_para_autoridad,
    importar_autoridades,
    proponer_cambios_sede,
    redistribuir_autoridades,
    responder_asignacion,
)
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.parametros.models import Sede, Turno
from apps.usuarios.permisos import puede_configurar_eleccion
from apps.usuarios.services import elector_de_identidad


def _cobertura_actual(eleccion_claustro):
    filas, sin_cubrir = [], []
    mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro).select_related("sede").order_by("numero")
    for mesa in mesas:
        for config in eleccion_claustro.turnos_autoridad.select_related("turno"):
            asignaciones = AsignacionAutoridad.objects.filter(mesa=mesa, turno=config.turno).exclude(estado=AsignacionAutoridad.Estado.RECHAZADA)
            titulares = asignaciones.filter(tipo=AsignacionAutoridad.Tipo.TITULAR).count()
            suplentes = asignaciones.filter(tipo=AsignacionAutoridad.Tipo.SUPLENTE).count()
            if not titulares:
                sin_cubrir.append((mesa, config.turno))
            filas.append({
                "mesa": mesa, "turno": config.turno,
                "titulares": titulares, "maximo_titulares": config.titulares_por_mesa,
                "suplentes_faltantes": max(0, config.suplentes_por_mesa - suplentes),
                "cubierta": titulares > 0,
            })
    return filas, sin_cubrir


@login_required
def descargar_plantilla_autoridades(request, eleccion_id, claustro_id=None):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para descargar la plantilla.")
    eleccion_claustro = None
    if claustro_id is not None:
        eleccion_claustro = get_object_or_404(
            EleccionClaustro.objects.select_related("claustro"),
            pk=claustro_id,
            eleccion=eleccion,
        )
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    sufijo = f"_{eleccion_claustro.claustro.nombre}" if eleccion_claustro else ""
    respuesta["Content-Disposition"] = f'attachment; filename="plantilla_autoridades_{eleccion.id}{sufijo}.csv"'
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(PLANTILLA_AUTORIDADES_HEADERS)
    for fila in PLANTILLA_AUTORIDADES_EJEMPLO:
        escritor.writerow(fila)
    return respuesta


@login_required
def gestionar_autoridades(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar autoridades.")

    resumen_claustros = []
    for eleccion_claustro in eleccion.elecciones_claustro.select_related("claustro").order_by("claustro__nombre"):
        alcance = {
            "registro_padron__eleccion_claustro_departamento__eleccion_claustro": eleccion_claustro,
        }
        asignaciones = AsignacionAutoridad.objects.filter(**alcance)
        resumen_claustros.append(
            {
                "eleccion_claustro": eleccion_claustro,
                "turnos": eleccion_claustro.turnos_autoridad.count(),
                "candidatos": CandidaturaAutoridad.objects.filter(**alcance).count(),
                "mesas": Mesa.objects.filter(
                    eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                ).count(),
                "asignadas": asignaciones.count(),
                "pendientes": asignaciones.filter(estado=AsignacionAutoridad.Estado.PENDIENTE).count(),
            }
        )
    return render(
        request,
        "autoridades/gestion.html",
        {
            "eleccion": eleccion,
            "resumen_claustros": resumen_claustros,
        },
    )


@login_required
def gestionar_autoridades_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    eleccion = eleccion_claustro.eleccion
    if not puede_configurar_eleccion(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar autoridades.")

    clave_propuesta = f"cambio_sede_autoridad_{eleccion.id}_{eleccion_claustro.id}"
    if request.method == "POST" and "cancelar-cambio-sede" in request.POST:
        request.session.pop(clave_propuesta, None)
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    if request.method == "POST" and "revisar-cambio-sede" in request.POST:
        mesa_destino = get_object_or_404(Mesa, pk=request.POST.get("mesa_destino"), eleccion=eleccion, eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro)
        turno_destino = get_object_or_404(eleccion_claustro.turnos_autoridad, turno_id=request.POST.get("turno_destino")).turno
        try:
            candidato_id = int(request.POST.get("candidatura_id"))
        except (TypeError, ValueError):
            candidato_id = -1
        propuestas = proponer_cambios_sede(eleccion_claustro, [(mesa_destino, turno_destino)])
        propuesta = next((p for p in propuestas if p["candidatura"].id == candidato_id), None)
        if propuesta is None:
            messages.error(request, "La propuesta ya no es válida; actualizá la cobertura e intentá de nuevo.")
        else:
            request.session[clave_propuesta] = {
                "registro_id": propuesta["registro"].id,
                "sede_id": propuesta["sede_destino"].id,
                "mesa_destino_id": propuesta["mesa_destino"].id,
                "turno_id": propuesta["turno"].id,
                "mesa_origen": propuesta["mesa_origen"].numero,
                "electores_mesa_origen": propuesta["electores_mesa_origen"],
            }
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    if request.method == "POST" and "confirmar-cambio-sede" in request.POST:
        datos = request.session.get(clave_propuesta)
        if not datos:
            messages.error(request, "No hay una propuesta de cambio vigente para confirmar.")
        else:
            registro = get_object_or_404(RegistroPadron, pk=datos["registro_id"], eleccion=eleccion)
            mesa_destino = get_object_or_404(Mesa, pk=datos["mesa_destino_id"], eleccion=eleccion, eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro)
            turno = get_object_or_404(eleccion_claustro.turnos_autoridad, turno_id=datos["turno_id"]).turno
            propuestas = proponer_cambios_sede(eleccion_claustro, [(mesa_destino, turno)])
            if not any(p["registro"].id == registro.id for p in propuestas):
                messages.error(request, "La propuesta ya no es válida; no se modificó el padrón.")
            else:
                try:
                    confirmar_cambio_sede_para_autoridad(registro, mesa_destino.sede, request.user)
                except (ValidationError, ValueError) as error:
                    detalle = error.messages[0] if isinstance(error, ValidationError) else str(error)
                    messages.error(request, f"No se pudo confirmar el cambio: {detalle}")
                else:
                    messages.success(request, "Cambio de sede confirmado. Se recalcularon las mesas y las asignaciones de autoridades.")
            request.session.pop(clave_propuesta, None)
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)

    configura_turnos = request.method == "POST" and "guardar-turnos" in request.POST
    agrega_candidato = request.method == "POST" and "agregar-candidato" in request.POST
    redistribuye = request.method == "POST" and "recalcular-autoridades" in request.POST
    quitar_candidato = request.method == "POST" and "quitar-candidato" in request.POST
    carga_candidatos = request.method == "POST" and "cargar-candidatos" in request.POST
    formulario_turnos = FormularioTurnosAutoridades(
        request.POST if configura_turnos else None,
        eleccion_claustro=eleccion_claustro,
        prefix="configuracion",
    )
    formulario_manual = FormularioBusquedaCandidato(request.POST if agrega_candidato else None, prefix="manual")
    formulario_csv = FormularioArchivoAutoridades(
        request.POST if carga_candidatos else None,
        request.FILES if carga_candidatos else None,
        prefix="csv",
    )
    if configura_turnos and formulario_turnos.is_valid():
        limites = []
        for turno in formulario_turnos.cleaned_data["turnos"]:
            existente = eleccion_claustro.turnos_autoridad.filter(turno=turno).first()
            try:
                titulares = int(request.POST.get(f"titulares_{turno.id}", existente.titulares_por_mesa if existente else 3))
                suplentes = int(request.POST.get(f"suplentes_{turno.id}", existente.suplentes_por_mesa if existente else 0))
            except (TypeError, ValueError):
                titulares, suplentes = 0, -1
            if not 1 <= titulares <= 32767 or not 0 <= suplentes <= 32767:
                formulario_turnos.add_error(None, "Cada turno requiere al menos un titular y los cupos deben ser números no negativos.")
                break
            limites.append((turno, titulares, suplentes))
        if formulario_turnos.errors:
            messages.error(request, "Revisá los cupos configurados para cada turno.")
        else:
            formulario_turnos.guardar()
            for turno, titulares, suplentes in limites:
                config = eleccion_claustro.turnos_autoridad.get(turno=turno)
                config.titulares_por_mesa = titulares
                config.suplentes_por_mesa = suplentes
                config.save(update_fields=("titulares_por_mesa", "suplentes_por_mesa"))
            if CandidaturaAutoridad.objects.filter(registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro, excluida=False).exists() and Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro).exists():
                try:
                    resumen = redistribuir_autoridades(eleccion_claustro, request.user)
                except ValidationError as error:
                    messages.warning(request, f"Configuración guardada; distribución pendiente: {error.messages[0]}")
                else:
                    messages.success(request, f"Turnos guardados y distribución actualizada ({resumen['asignadas']} asignaciones).")
            else:
                messages.success(request, f"Turnos de {eleccion_claustro.claustro} actualizados.")
            return redirect(
                "gestionar-autoridades-claustro",
                eleccion_id=eleccion.id,
                claustro_id=eleccion_claustro.id,
            )
    if agrega_candidato and formulario_manual.is_valid():
        if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
            formulario_manual.add_error(None, "La nómina no puede cambiarse después de emitir el padrón imprimible.")
            padrones = RegistroPadron.objects.none()
        else:
            from django.db.models import Q
            termino = formulario_manual.cleaned_data["busqueda"].strip()
            padrones = RegistroPadron.objects.filter(
                eleccion=eleccion,
                eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                activo=True,
            ).filter(
                Q(elector__dni__icontains=termino) | Q(elector__legajo__icontains=termino)
                | Q(elector__nombre__icontains=termino) | Q(elector__apellido__icontains=termino)
            )
        if formulario_manual.errors:
            pass
        elif padrones.count() != 1:
            formulario_manual.add_error("busqueda", "La búsqueda debe identificar a un único elector activo del padrón de este claustro.")
        else:
            candidatura, _ = CandidaturaAutoridad.objects.get_or_create(
                registro_padron=padrones.select_related("asignacion_mesa__mesa").first(),
                defaults={"cargada_por": request.user},
            )
            candidatura.excluida = False
            candidatura.save(update_fields=("excluida",))
            try:
                resumen = redistribuir_autoridades(eleccion_claustro, request.user)
            except ValidationError as error:
                messages.warning(request, f"Candidato guardado. La distribución queda pendiente: {error.messages[0]}")
            else:
                messages.success(request, f"Candidato agregado. Se asignaron {resumen['asignadas']} autoridades; quedan {len(resumen['sin_cubrir'])} mesas-turno sin titular.")
                return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    if redistribuye:
        try:
            resumen = redistribuir_autoridades(eleccion_claustro, request.user)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, f"Distribución recalculada: {resumen['asignadas']} asignaciones y {len(resumen['sin_cubrir'])} mesas-turno sin titular.")
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    if quitar_candidato:
        if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
            messages.error(request, "No se puede modificar la nómina después de emitir el padrón imprimible.")
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
        candidatura = get_object_or_404(CandidaturaAutoridad, pk=request.POST.get("candidatura_id"), registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro)
        if request.POST.get("modo") == "excluir":
            candidatura.excluida = True
            candidatura.save(update_fields=("excluida",))
            recalcular = True
        else:
            recalcular = False
        asignacion_actual = AsignacionAutoridad.objects.filter(registro_padron=candidatura.registro_padron).first()
        if asignacion_actual:
            from apps.usuarios.models import AsignacionRol, PerfilUsuario
            perfil = PerfilUsuario.objects.filter(elector=candidatura.registro_padron.elector).first()
            if perfil:
                AsignacionRol.objects.filter(rol=AsignacionRol.Rol.AUTORIDAD_MESA, eleccion=eleccion, mesa=asignacion_actual.mesa, usuario=perfil.usuario).delete()
            asignacion_actual.delete()
        if recalcular:
            try:
                redistribuir_autoridades(eleccion_claustro, request.user)
            except ValidationError as error:
                messages.warning(request, f"Se guardó la exclusión. La distribución queda pendiente: {error.messages[0]}")
                return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
        messages.success(request, "Elector excluido de futuras distribuciones." if recalcular else "Se liberó la asignación actual; puede volver a ser seleccionado al recalcular.")
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    errores_importacion = []
    errores_importacion_total = 0
    if carga_candidatos and formulario_csv.is_valid():
        cantidad, errores = importar_autoridades(
            formulario_csv.cleaned_data["archivo"].read(),
            eleccion_claustro,
            request.user,
            formulario_csv.cleaned_data["archivo"].name,
        )
        if errores:
            errores_importacion_total = len(errores)
            errores_importacion = [
                {"fila": fila, "mensaje": mensaje}
                for fila, mensaje in errores[:10]
            ]
        else:
            messages.success(request, f"Se cargaron {cantidad} candidatos desde el archivo y se recalculó su distribución.")
            return redirect(
                "gestionar-autoridades-claustro",
                eleccion_id=eleccion.id,
                claustro_id=eleccion_claustro.id,
            )
    autoridades = AsignacionAutoridad.objects.filter(
        mesa__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related("registro_padron__elector", "mesa", "turno", "asignada_por")
    candidatos = CandidaturaAutoridad.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related("registro_padron__elector", "registro_padron__sede", "registro_padron__turno_cursada").order_by("registro_padron__elector__apellido", "registro_padron__elector__nombre")
    cobertura, sin_cubrir = _cobertura_actual(eleccion_claustro)
    propuestas_sede = proponer_cambios_sede(eleccion_claustro, sin_cubrir)
    datos_propuesta = request.session.get(clave_propuesta)
    propuesta_sede = None
    if datos_propuesta:
        propuesta_sede = {
            **datos_propuesta,
            "registro": get_object_or_404(RegistroPadron.objects.select_related("elector", "asignacion_sede_padron__sede"), pk=datos_propuesta["registro_id"]),
            "sede_destino": get_object_or_404(Sede, pk=datos_propuesta["sede_id"]),
            "mesa_destino": get_object_or_404(Mesa, pk=datos_propuesta["mesa_destino_id"]),
            "turno": get_object_or_404(Turno, pk=datos_propuesta["turno_id"]),
        }
    return render(
        request,
        "autoridades/gestion_claustro.html",
        {
            "eleccion": eleccion,
            "eleccion_claustro": eleccion_claustro,
            "formulario_turnos": formulario_turnos,
            "formulario_manual": formulario_manual,
            "formulario_csv": formulario_csv,
            "errores_importacion": errores_importacion,
            "errores_importacion_total": errores_importacion_total,
            "candidatos": candidatos,
            "configuraciones_turnos": eleccion_claustro.turnos_autoridad.select_related("turno").order_by("turno__hora_inicio"),
            "cobertura": cobertura,
            "propuestas_sede": propuestas_sede,
            "propuesta_sede": propuesta_sede,
            "autoridades": autoridades,
        },
    )


@login_required
def mis_asignaciones_autoridad(request):
    elector = elector_de_identidad(request.user)
    asignaciones = AsignacionAutoridad.objects.select_related("mesa__sede", "turno", "registro_padron__eleccion", "registro_padron__elector")
    if request.user.is_superuser:
        return render(request, "autoridades/mis_asignaciones.html", {"asignaciones": asignaciones, "vista_administrativa": True})
    if elector is not None:
        asignaciones = asignaciones.filter(registro_padron__elector=elector)
        if not asignaciones.exists():
            return HttpResponseForbidden("No tiene asignaciones de autoridad de mesa.")
    elif getattr(request.user, "es_elector", False) or not request.user.asignaciones_rol.filter(rol="autoridad_mesa", activo=True).exists():
        return HttpResponseForbidden("No tiene permiso de autoridad de mesa.")
    else:
        asignaciones = asignaciones.none()
    return render(request, "autoridades/mis_asignaciones.html", {"asignaciones": asignaciones})


@login_required
def responder_autoridad(request, asignacion_id):
    if request.method != "POST":
        raise Http404()
    asignacion = get_object_or_404(AsignacionAutoridad, pk=asignacion_id, registro_padron__elector=elector_de_identidad(request.user))
    responder_asignacion(asignacion, request.POST.get("respuesta") == "aceptar")
    messages.success(request, "La respuesta fue registrada.")
    return redirect("mis-asignaciones-autoridad")


@login_required
def preferencia_autoridad(request, asignacion_id):
    asignacion = get_object_or_404(AsignacionAutoridad.objects.select_related("registro_padron__eleccion"), pk=asignacion_id, registro_padron__elector=elector_de_identidad(request.user))
    preferencia, _ = PreferenciaAutoridad.objects.get_or_create(registro_padron=asignacion.registro_padron)
    formulario = FormularioPreferenciaAutoridad(
        request.POST or None,
        instance=preferencia,
        registro_padron=asignacion.registro_padron,
    )
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, "La preferencia fue actualizada.")
        return redirect("mis-asignaciones-autoridad")
    return render(request, "autoridades/preferencia.html", {"asignacion": asignacion, "formulario": formulario})
