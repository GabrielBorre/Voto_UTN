import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from apps.autoridades.forms import (
    FormularioArchivoNomina,
    FormularioBusquedaCandidato,
    FormularioPreferenciaAutoridad,
    FormularioTurnosAutoridades,
    FormularioConfiguracionAutoridades,
    FormularioSeleccionMesa,
    FormularioFiltroAsignaciones,
)
from apps.autoridades.distribucion import configuracion_actual, bloquear_edicion, guardar_selecciones
from apps.autoridades.services import (
    PLANTILLA_NOMINA_HEADERS,
    redistribuir_autoridades,
    responder_asignacion,
)
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
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
            sin_cubrir.extend([(mesa, config.turno)] * max(0, config.titulares_por_mesa - titulares))
            filas.append({
                "mesa": mesa, "turno": config.turno,
                "titulares": titulares, "maximo_titulares": config.titulares_por_mesa,
                "suplentes": suplentes, "maximo_suplentes": config.suplentes_por_mesa,
                "suplentes_faltantes": max(0, config.suplentes_por_mesa - suplentes),
                "cubierta": titulares >= config.titulares_por_mesa,
            })
    return filas, sin_cubrir


@login_required
def descargar_plantilla_autoridades(request, eleccion_id, claustro_id=None):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
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
    escritor.writerow(PLANTILLA_NOMINA_HEADERS)
    return respuesta


@login_required
def gestionar_autoridades(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
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
                "asignadas": asignaciones.exclude(estado=AsignacionAutoridad.Estado.RECHAZADA).count(),
                "rechazadas": asignaciones.filter(estado=AsignacionAutoridad.Estado.RECHAZADA).count(),
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
@transaction.atomic
def gestionar_autoridades_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    eleccion = eleccion_claustro.eleccion
    if not puede_configurar_eleccion(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
        return HttpResponseForbidden("No tiene permiso para gestionar autoridades.")

    clave_propuesta = f"cambio_sede_autoridad_{eleccion.id}_{eleccion_claustro.id}"
    clave_nomina = f"propuesta_nomina_{eleccion.id}_{eleccion_claustro.id}"
    clave_comparacion = f"comparacion_nomina_{eleccion.id}_{eleccion_claustro.id}"
    opciones = configuracion_actual(eleccion_claustro)
    modo_anterior = opciones.modo
    actualizar_nomina = request.method == "POST" and "actualizar-nomina" in request.POST
    aplicar_modo = request.method == "POST" and ("aplicar-modo" in request.POST or actualizar_nomina)
    if aplicar_modo and request.POST.get("modo") == "manual":
        # Compatibilidad con formularios antiguos: Manual solo abre la edición.
        return redirect(f"{request.path}#asignaciones")
    formulario_modo = FormularioConfiguracionAutoridades(request.POST if aplicar_modo else None, instance=opciones)
    formulario_nomina = FormularioArchivoNomina(
        request.POST if aplicar_modo and request.POST.get("modo") == "nomina" else None,
        request.FILES if aplicar_modo and request.POST.get("modo") == "nomina" else None,
    )
    formulario_nomina.fields["archivo"].required = bool(
        aplicar_modo and request.POST.get("modo") == "nomina" and not actualizar_nomina
    )
    if request.method == "POST" and "cancelar-nomina" in request.POST:
        request.session.pop(clave_nomina, None)
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST":
        try:
            with transaction.atomic():
                bloquear_edicion(eleccion_claustro)
        except ValidationError as error:
            if "confirmar-nomina" in request.POST:
                request.session.pop(clave_nomina, None)
            messages.error(request, error.messages[0])
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and "confirmar-nomina" in request.POST:
        from apps.autoridades.nomina import confirmar_nomina
        propuesta = request.session.get(clave_nomina)
        if not propuesta:
            messages.error(request, "No hay una previsualización pendiente. Volvé a calcular la nómina.")
        else:
            try:
                resumen = confirmar_nomina(eleccion_claustro, request.user, propuesta)
            except ValidationError as error:
                messages.error(request, "No se aplicó la nómina: " + " ".join(error.messages))
            else:
                messages.success(request, f"Se asignaron {resumen['titulares']} titulares y {resumen['suplentes']} suplentes; {resumen['sin_asignar']} personas quedaron sin asignar.")
                from apps.autoridades.nomina import previsualizar_nomina
                try:
                    datos_actuales = {**propuesta["datos"], "registros": []}
                    comparacion = previsualizar_nomina(eleccion_claustro, request.user, datos_actuales)
                except ValidationError:
                    request.session.pop(clave_comparacion, None)
                else:
                    request.session[clave_comparacion] = {"estado": comparacion["estado"], "alternativas": comparacion["alternativas"]}
            request.session.pop(clave_nomina, None)
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and "recalcular-distribucion" in request.POST:
        try:
            resumen = redistribuir_autoridades(
                eleccion_claustro, request.user, preservar_asignaciones=False,
            )
            request.session.pop(clave_nomina, None)
            messages.success(
                request,
                f"Distribución recalculada: {resumen['asignadas']} autoridades. "
                f"Se reasignaron desde cero. Faltan "
                f"{resumen['titulares_faltantes']} titulares y {resumen['suplentes_faltantes']} suplentes.",
            )
            if resumen["titulares_faltantes"] or resumen["suplentes_faltantes"]:
                messages.warning(request, "Se alcanzó la mayor cobertura posible: no hay una combinación compatible que cubra más cupos respetando la prioridad de titulares, el padrón y los turnos actuales.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and "eliminar-asignaciones" in request.POST:
        if request.POST.get("confirmar-eliminacion") != "1":
            messages.error(request, "Confirmá la eliminación de todas las asignaciones antes de continuar.")
        else:
            from apps.autoridades.distribucion import eliminar_asignaciones
            try:
                cantidad = eliminar_asignaciones(eleccion_claustro, request.user)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                request.session.pop(clave_propuesta, None)
                request.session.pop(clave_nomina, None)
                messages.success(request, f"Se eliminaron {cantidad} asignaciones de autoridades de este claustro. Las mesas quedaron sin autoridades; podés volver a asignarlas cuando lo necesites.")
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if aplicar_modo and formulario_modo.is_valid():
        modo_elegido = formulario_modo.cleaned_data["modo"]
        if modo_elegido == "nomina":
            if actualizar_nomina and modo_anterior != "nomina":
                formulario_nomina.add_error("archivo", "Cargá el archivo de nómina para iniciar la nómina común.")
            elif formulario_nomina.is_valid():
                from apps.autoridades.nomina import identificar_nomina, previsualizar_nomina
                try:
                    archivo = formulario_nomina.cleaned_data["archivo"]
                    registros = identificar_nomina(eleccion_claustro, archivo.read(), archivo.name) if archivo else []
                    datos = {"registros": registros, "mesa": formulario_modo.cleaned_data["reacomodar_titulares"],
                             "votar_mesa": formulario_modo.cleaned_data["permitir_mesa_distinta"],
                             "sede": formulario_modo.cleaned_data["permitir_cambio_sede"]}
                    request.session[clave_nomina] = previsualizar_nomina(eleccion_claustro, request.user, datos)
                except ValidationError as error:
                    formulario_nomina.add_error("archivo", " ".join(error.messages))
                else:
                    return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
            # Los errores se muestran junto al archivo, sin cambiar el modo guardado.
        elif modo_elegido == "manual":
            return redirect(f"{request.path}?modo_vista=manual#asignaciones")
        if modo_elegido == "nomina":
            pass
        elif not eleccion_claustro.turnos_autoridad.exists() or not Mesa.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        ).exists():
            messages.error(request, "Configurá al menos un turno y verificá que haya mesas antes de aplicar la distribución.")
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
        else:
            try:
                with transaction.atomic():
                    bloquear_edicion(eleccion_claustro)
                    opciones = formulario_modo.save()
                    from apps.autoridades.distribucion import _auditar
                    _auditar(eleccion_claustro, request.user, "autoridades.configuracion", {
                        "modo": opciones.modo,
                        "permitir_cambio_sede": opciones.permitir_cambio_sede,
                        "reacomodar_titulares": opciones.reacomodar_titulares,
                        "permitir_mesa_distinta": opciones.permitir_mesa_distinta,
                    })
                    if eleccion_claustro.turnos_autoridad.exists() and Mesa.objects.filter(
                        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                    ).exists():
                        resumen = redistribuir_autoridades(eleccion_claustro, request.user)
                        mensaje = (
                            f"Distribución aplicada: {resumen['asignadas']} autoridades. "
                            f"Se conservaron {resumen['conservadas']}, se incorporaron {resumen['nuevas']} "
                            f"y se liberaron {resumen['liberadas']}. Faltan "
                            f"{resumen['titulares_faltantes']} titulares y {resumen['suplentes_faltantes']} suplentes."
                        )
                        if modo_elegido == "aleatorio" and (resumen["titulares_faltantes"] or resumen["suplentes_faltantes"]):
                            mensaje += " No se pueden cubrir más cupos conservando las asignaciones y selecciones actuales. Recalcular permite sortear todo desde cero."
                    else:
                        mensaje = "Modo aplicado. Configurá al menos un turno y verificá que haya mesas para distribuir."
                messages.success(request, mensaje)
                request.session.pop(clave_nomina, None)
            except ValidationError as error:
                messages.error(request, f"No se aplicó la distribución: {error.messages[0]}")
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and "aplicar-distribucion" in request.POST:
        if opciones.modo == "manual":
            return redirect(f"{request.path}?modo_vista=manual#asignaciones")
        if opciones.modo == "nomina":
            from apps.autoridades.nomina import previsualizar_nomina
            try:
                datos = {"registros": [], "mesa": opciones.reacomodar_titulares,
                         "votar_mesa": opciones.permitir_mesa_distinta, "sede": opciones.permitir_cambio_sede}
                request.session[clave_nomina] = previsualizar_nomina(eleccion_claustro, request.user, datos)
            except ValidationError as error:
                messages.error(request, "No se pudo calcular la propuesta: " + " ".join(error.messages))
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
        try:
            resumen = redistribuir_autoridades(eleccion_claustro, request.user)
            request.session.pop(clave_nomina, None)
            messages.success(request, f"Distribución aplicada: {resumen['asignadas']} autoridades. Faltan {resumen['titulares_faltantes']} titulares y {resumen['suplentes_faltantes']} suplentes; completá los cupos pendientes.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and opciones.modo != "nomina" and any(k in request.POST for k in ("agregar-candidato", "cargar-candidatos")):
        messages.error(request, "Usá la selección por mesa o el sorteo del modo elegido.")
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and "cancelar-cambio-sede" in request.POST:
        request.session.pop(clave_propuesta, None)
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    if request.method == "POST" and any(accion in request.POST for accion in ("revisar-cambio-sede", "confirmar-cambio-sede")):
        request.session.pop(clave_propuesta, None)
        messages.error(request, "Para cambiar de sede, revisá y confirmá la propuesta de nómina.")
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)

    configura_turnos = request.method == "POST" and "guardar-turnos" in request.POST
    agrega_candidato = request.method == "POST" and "agregar-candidato" in request.POST
    quitar_candidato = request.method == "POST" and "quitar-candidato" in request.POST
    carga_candidatos = request.method == "POST" and "cargar-candidatos" in request.POST
    formulario_turnos = FormularioTurnosAutoridades(
        request.POST if configura_turnos else None,
        eleccion_claustro=eleccion_claustro,
        prefix="configuracion",
    )
    formulario_manual = FormularioBusquedaCandidato(request.POST if agrega_candidato else None, prefix="manual")
    formulario_csv = FormularioArchivoNomina(
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
            from django.db.models import Count
            asignaciones = AsignacionAutoridad.objects.filter(
                mesa__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                estado=AsignacionAutoridad.Estado.ASIGNADA, turno=turno,
            ).values("mesa_id", "tipo").annotate(cantidad=Count("id"))
            if any(fila["cantidad"] > (titulares if fila["tipo"] == "titular" else suplentes) for fila in asignaciones):
                formulario_turnos.add_error(None, "Quitá o modificá las asignaciones que exceden el nuevo cupo antes de reducirlo.")
                break
            if opciones.modo == "manual":
                selecciones = CandidaturaAutoridad.objects.filter(
                    registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                    excluida=False, mesa_manual__isnull=False, turno_manual=turno,
                ).values("mesa_manual_id", "tipo_manual").annotate(cantidad=Count("id"))
                if any(fila["cantidad"] > (titulares if fila["tipo_manual"] == "titular" else suplentes) for fila in selecciones):
                    formulario_turnos.add_error(None, "Quitá las selecciones manuales que exceden el nuevo cupo antes de reducirlo.")
                    break
            limites.append((turno, titulares, suplentes))
        if formulario_turnos.errors:
            messages.error(request, "Revisá los cupos configurados para cada turno.")
        else:
            try:
                with transaction.atomic():
                    formulario_turnos.guardar()
                    for turno, titulares, suplentes in limites:
                        config = eleccion_claustro.turnos_autoridad.get(turno=turno)
                        config.titulares_por_mesa = titulares
                        config.suplentes_por_mesa = suplentes
                        config.save(update_fields=("titulares_por_mesa", "suplentes_por_mesa"))
                    puede_previsualizar = opciones.modo == "nomina" and bool(limites) and Mesa.objects.filter(
                        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                    ).exists() and CandidaturaAutoridad.objects.filter(
                        registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
                    ).exists()
                    if puede_previsualizar:
                        from apps.autoridades.nomina import previsualizar_nomina
                        datos = {"registros": [], "mesa": opciones.reacomodar_titulares,
                                 "votar_mesa": opciones.permitir_mesa_distinta, "sede": opciones.permitir_cambio_sede}
                        request.session[clave_nomina] = previsualizar_nomina(eleccion_claustro, request.user, datos)
                    elif opciones.modo == "nomina":
                        request.session.pop(clave_nomina, None)
                mensaje = ("Revisá la distribución propuesta." if puede_previsualizar else
                           "Configurá mesas y turnos y cargá la nómina para revisar la distribución." if opciones.modo == "nomina" else
                           "Aplicá el modo elegido para distribuir.")
                messages.success(request, f"Turnos y cupos de {eleccion_claustro.claustro} actualizados. {mensaje}")
            except ValidationError as error:
                messages.error(request, f"No se guardaron los turnos y cupos: {error.messages[0]}")
            return redirect(
                "gestionar-autoridades-claustro",
                eleccion_id=eleccion.id,
                claustro_id=eleccion_claustro.id,
            )
    if agrega_candidato:
        messages.error(request, "La nómina común se carga con el archivo de nómina.")
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if quitar_candidato:
        if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
            messages.error(request, "No se puede modificar la nómina después de emitir el padrón imprimible.")
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
        candidatura = get_object_or_404(CandidaturaAutoridad, pk=request.POST.get("candidatura_id"), registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro)
        candidatura.excluida = not candidatura.excluida
        if candidatura.excluida:
            candidatura.mesa_traslado = None
            candidatura.turno_traslado = None
            candidatura.mesa_manual = None
            candidatura.turno_manual = None
            candidatura.tipo_manual = ""
            candidatura.orden_manual = None
        candidatura.save(update_fields=("excluida", "mesa_manual", "turno_manual", "tipo_manual", "orden_manual", "mesa_traslado", "turno_traslado"))
        asignacion_actual = AsignacionAutoridad.objects.filter(registro_padron=candidatura.registro_padron).first()
        if asignacion_actual:
            from apps.usuarios.models import AsignacionRol, PerfilUsuario
            perfil = PerfilUsuario.objects.filter(elector=candidatura.registro_padron.elector).first()
            if perfil:
                AsignacionRol.objects.filter(rol=AsignacionRol.Rol.AUTORIDAD_MESA, eleccion=eleccion, mesa=asignacion_actual.mesa, usuario=perfil.usuario).delete()
            asignacion_actual.delete()
            if candidatura.excluida and asignacion_actual.tipo == AsignacionAutoridad.Tipo.TITULAR:
                from apps.autoridades.distribucion import promover_suplente_por_baja
                promover_suplente_por_baja(asignacion_actual.mesa, asignacion_actual.turno, request.user)
        if candidatura.excluida:
            mensaje = "Elector quitado de la nómina de autoridades; sigue habilitado para votar."
        else:
            mensaje = "Elector reincorporado a la nómina de autoridades."
        if opciones.modo == "nomina":
            from apps.autoridades.nomina import previsualizar_nomina
            try:
                datos = {"registros": [], "mesa": opciones.reacomodar_titulares,
                         "votar_mesa": opciones.permitir_mesa_distinta, "sede": opciones.permitir_cambio_sede}
                request.session[clave_nomina] = previsualizar_nomina(eleccion_claustro, request.user, datos)
            except ValidationError as error:
                messages.warning(request, f"{mensaje} La propuesta queda pendiente: {error.messages[0]}")
            else:
                messages.success(request, f"{mensaje} Revisá la distribución propuesta.")
            return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
        try:
            resumen = redistribuir_autoridades(eleccion_claustro, request.user)
        except ValidationError as error:
            messages.warning(request, f"{mensaje} La distribución queda pendiente: {error.messages[0]}")
        else:
            messages.success(
                request,
                f"{mensaje} Se recalculó la distribución: {resumen['asignadas']} asignaciones; "
                f"{len(resumen['sin_cubrir'])} mesas-turno sin titular.",
            )
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    errores_importacion = []
    errores_importacion_total = 0
    if carga_candidatos and formulario_csv.is_valid():
        from apps.autoridades.nomina import identificar_nomina, previsualizar_nomina
        archivo = formulario_csv.cleaned_data["archivo"]
        try:
            registros = identificar_nomina(eleccion_claustro, archivo.read(), archivo.name)
            datos = {"registros": registros, "mesa": opciones.reacomodar_titulares,
                     "votar_mesa": opciones.permitir_mesa_distinta, "sede": opciones.permitir_cambio_sede}
            request.session[clave_nomina] = previsualizar_nomina(eleccion_claustro, request.user, datos)
        except ValidationError as error:
            messages.error(request, "No se pudo calcular la propuesta: " + " ".join(error.messages))
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=eleccion_claustro.id)
    autoridades = AsignacionAutoridad.objects.filter(
        mesa__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related("registro_padron__elector", "mesa", "turno", "asignada_por", "reemplazada_por__registro_padron__elector")
    candidatos = CandidaturaAutoridad.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related("registro_padron__elector", "registro_padron__sede", "registro_padron__turno_cursada").order_by("registro_padron__elector__apellido", "registro_padron__elector__nombre")
    cobertura, sin_cubrir = _cobertura_actual(eleccion_claustro)
    pagina_nomina = Paginator(candidatos, 25).get_page(request.GET.get("pagina_nomina", 1))
    mesas_con_asignaciones = Mesa.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).select_related("sede", "eleccion_claustro_departamento__departamento").order_by("numero")
    formulario_filtros = FormularioFiltroAsignaciones(request.GET, claustro=eleccion_claustro)
    if formulario_filtros.is_valid():
        filtros = formulario_filtros.cleaned_data
        if filtros["departamento"]:
            mesas_con_asignaciones = mesas_con_asignaciones.filter(
                eleccion_claustro_departamento__departamento=filtros["departamento"],
            )
        if filtros["sede"]:
            mesas_con_asignaciones = mesas_con_asignaciones.filter(sede=filtros["sede"])
        sin_titulares = {f["mesa"].pk for f in cobertura if not f["cubierta"]}
        sin_suplentes = {f["mesa"].pk for f in cobertura if f["suplentes_faltantes"]}
        if filtros["cobertura"] == "titulares":
            mesas_con_asignaciones = mesas_con_asignaciones.filter(pk__in=sin_titulares)
        elif filtros["cobertura"] == "suplentes":
            mesas_con_asignaciones = mesas_con_asignaciones.filter(pk__in=sin_suplentes)
        elif filtros["cobertura"] == "completa":
            mesas_con_asignaciones = mesas_con_asignaciones.filter(
                pk__in={f["mesa"].pk for f in cobertura} - sin_titulares - sin_suplentes,
            )
    else:
        mesas_con_asignaciones = mesas_con_asignaciones.none()
    parametros_mesas = request.GET.copy()
    parametros_mesas.pop("pagina_mesas", None)
    pagina_mesas = Paginator(mesas_con_asignaciones, 25).get_page(request.GET.get("pagina_mesas", 1))
    autoridades_por_mesa = {}
    cobertura_por_mesa = {}
    for asignacion in autoridades.filter(mesa__in=pagina_mesas.object_list).order_by(
        "mesa__numero", "turno__hora_inicio",
        Case(When(tipo=AsignacionAutoridad.Tipo.TITULAR, then=Value(0)), default=Value(1), output_field=IntegerField()),
        "orden_suplencia", "registro_padron__elector__apellido", "registro_padron__elector__nombre",
    ):
        autoridades_por_mesa.setdefault(asignacion.mesa_id, []).append(asignacion)
    for fila in cobertura:
        cobertura_por_mesa.setdefault(fila["mesa"].pk, []).append(fila)
    for mesa in pagina_mesas.object_list:
        mesa.autoridades_pagina = autoridades_por_mesa.get(mesa.pk, [])
        mesa.cobertura_pagina = cobertura_por_mesa.get(mesa.pk, [])
    modo_vista = "aleatorio" if opciones.modo == "manual" else opciones.modo
    if aplicar_modo and request.POST.get("modo") in ("nomina", "aleatorio"):
        modo_vista = request.POST["modo"]
    resumen_nomina = None
    if opciones.modo == "nomina":
        from apps.autoridades.nomina import _huella, resumen_actual
        resumen_nomina = resumen_actual(eleccion_claustro)
        comparacion = request.session.get(clave_comparacion)
        if comparacion and comparacion["estado"] == _huella(eleccion_claustro):
            resumen_nomina["escenarios"] = comparacion["alternativas"]
    turnos_configurados = set(eleccion_claustro.turnos_autoridad.values_list("turno_id", flat=True))
    configuraciones_por_turno = {
        configuracion.turno_id: configuracion
        for configuracion in eleccion_claustro.turnos_autoridad.select_related("turno")
    }
    configuraciones_turnos = []
    for turno in formulario_turnos.fields["turnos"].queryset:
        configuracion = configuraciones_por_turno.get(turno.pk)
        configuraciones_turnos.append({
            "turno": turno,
            "turno_id": turno.pk,
            "titulares_por_mesa": configuracion.titulares_por_mesa if configuracion else 3,
            "suplentes_por_mesa": configuracion.suplentes_por_mesa if configuracion else 0,
        })
    return render(
        request,
        "autoridades/gestion_claustro.html",
        {
            "eleccion": eleccion,
            "eleccion_claustro": eleccion_claustro,
            "formulario_turnos": formulario_turnos,
            "formulario_modo": formulario_modo,
            "formulario_nomina": formulario_nomina,
            "opciones": opciones,
            "modo_vista": modo_vista,
            "modo_guardado": modo_anterior,
            "resumen_nomina": resumen_nomina,
            "propuesta_nomina": request.session.get(clave_nomina),
            "turnos_configurados": turnos_configurados,
            "mesas_seleccion": Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro).select_related("sede"),
            "titulares_faltantes": len(sin_cubrir),
            "suplentes_faltantes": sum(fila["suplentes_faltantes"] for fila in cobertura),
            "formulario_manual": formulario_manual,
            "formulario_csv": formulario_csv,
            "errores_importacion": errores_importacion,
            "errores_importacion_total": errores_importacion_total,
            "pagina_nomina": pagina_nomina,
            "configuraciones_turnos": configuraciones_turnos,
            "cobertura": cobertura,
            "pagina_mesas": pagina_mesas,
            "formulario_filtros": formulario_filtros,
            "filtros_activos": any(request.GET.get(campo) for campo in formulario_filtros.fields),
            "parametros_mesas": parametros_mesas.urlencode(),
            "cantidad_autoridades_listado": autoridades.filter(mesa__in=mesas_con_asignaciones).count(),
            "cantidad_autoridades": autoridades.count(),
        },
    )


@login_required
def seleccionar_autoridades_mesa(request, eleccion_id, claustro_id, mesa_id):
    from apps.autoridades.seleccion_manual import asignar_manualmente, quitar_designacion
    mesa = get_object_or_404(Mesa.objects.select_related("eleccion", "eleccion_claustro_departamento__eleccion_claustro", "sede"), pk=mesa_id, eleccion_id=eleccion_id, eleccion_claustro_departamento__eleccion_claustro_id=claustro_id)
    claustro = mesa.eleccion_claustro_departamento.eleccion_claustro
    if not puede_configurar_eleccion(request.user, mesa.eleccion):
        return HttpResponseForbidden("No tiene permiso para seleccionar autoridades.")
    formulario = FormularioSeleccionMesa(
        request.POST if "seleccionar" in request.POST else None, mesa=mesa,
        initial={"turno": request.GET.get("turno"), "tipo": request.GET.get("tipo", "titular"),
                 "asignacion_a_reemplazar": request.GET.get("reemplazar")},
    )
    if request.method == "GET" and request.GET.get("reemplazar") and formulario.reemplazo is None:
        raise Http404("La designación ya no está disponible en esta mesa.")
    if request.method == "POST":
        try:
            if "seleccionar" in request.POST and formulario.is_valid():
                d = formulario.cleaned_data
                asignar_manualmente(mesa, d["turno"], d["registro"], request.user,
                                   tipo=d["tipo"], orden=d["orden"], reemplazar=d["asignacion_a_reemplazar"])
                request.session.pop(f"propuesta_nomina_{eleccion_id}_{claustro_id}", None)
                messages.success(request, "Designación guardada en el cupo elegido.")
                return redirect(f"{request.path}?turno={d['turno'].pk}&tipo={d['tipo']}#autoridades-mesa")
            if "quitar-asignacion" in request.POST:
                try:
                    asignacion_id = int(request.POST.get("quitar-asignacion", ""))
                except (ValueError, TypeError):
                    raise ValidationError("Elegí una designación válida de esta mesa.")
                quitar_designacion(mesa, asignacion_id, request.user)
                request.session.pop(f"propuesta_nomina_{eleccion_id}_{claustro_id}", None)
                messages.success(request, "Designación quitada. El cupo quedó disponible para elegir otra persona.")
                return redirect(f"{request.path}#autoridades-mesa")
            if "importar" in request.POST or request.FILES:
                messages.error(request, "La edición manual se realiza eligiendo personas, sin cargar archivos.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    autoridades = list(mesa.autoridades.select_related("registro_padron__elector", "turno", "candidatura").order_by(
        "turno__hora_inicio", Case(When(tipo="titular", then=Value(0)), default=Value(1), output_field=IntegerField()),
        "orden_suplencia", "registro_padron__elector__apellido", "registro_padron__elector__nombre",
    ))
    cobertura_mesa = []
    for config in claustro.turnos_autoridad.select_related("turno").order_by("turno__hora_inicio"):
        cobertura_mesa.append({
            "turno": config.turno, "maximo_titulares": config.titulares_por_mesa, "maximo_suplentes": config.suplentes_por_mesa,
            "titulares": sum(a.turno_id == config.turno_id and a.tipo == "titular" and a.estado == "asignada" for a in autoridades),
            "suplentes": sum(a.turno_id == config.turno_id and a.tipo == "suplente" and a.estado == "asignada" for a in autoridades),
        })
    return render(request, "autoridades/seleccionar_mesa.html", {
        "eleccion": mesa.eleccion, "mesa": mesa, "eleccion_claustro": claustro,
        "formulario": formulario, "autoridades": autoridades, "cobertura_mesa": cobertura_mesa,
        "personas_disponibles": formulario.datos_personas,
    })


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
    if request.POST.get("respuesta") != "rechazar":
        messages.error(request, "La asignación ya es válida. Solo necesitás responder si la rechazás.")
    elif asignacion.estado == AsignacionAutoridad.Estado.RECHAZADA:
        messages.info(request, "La asignación ya figura como rechazada.")
    else:
        eleccion_claustro = asignacion.mesa.eleccion_claustro_departamento.eleccion_claustro
        try:
            responder_asignacion(asignacion)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Se registró que no asistirás. La Junta confirmará el reemplazo; el justificativo se evalúa por separado.")
    return redirect("mis-asignaciones-autoridad")


@login_required
def confirmar_reemplazo_autoridad(request, asignacion_id):
    from apps.autoridades.reemplazos import confirmar_reemplazo, puede_confirmar_reemplazo
    if request.method != "POST":
        raise Http404()
    asignacion = get_object_or_404(AsignacionAutoridad.objects.select_related("registro_padron__eleccion", "mesa__eleccion_claustro_departamento"), pk=asignacion_id)
    if not puede_confirmar_reemplazo(request.user, asignacion.registro_padron.eleccion):
        return HttpResponseForbidden("No tiene permiso para confirmar este reemplazo.")
    try:
        promovida = confirmar_reemplazo(asignacion, request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Reemplazo confirmado: se promovió al suplente." if promovida else "Ausencia confirmada. No hay suplente disponible; revisá la vacante.")
    return redirect("gestionar-autoridades-claustro", eleccion_id=asignacion.registro_padron.eleccion_id, claustro_id=asignacion.mesa.eleccion_claustro_departamento.eleccion_claustro_id)


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
