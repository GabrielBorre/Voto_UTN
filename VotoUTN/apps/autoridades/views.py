import csv
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date

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
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ImportacionNominaAutoridades, PreferenciaAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.usuarios.permisos import puede_gestionar_autoridades
from apps.usuarios.services import elector_de_identidad


def _cobertura_actual(eleccion_claustro):
    filas, sin_cubrir = [], []
    mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro).select_related("sede").order_by("numero")
    for mesa in mesas:
        for config in eleccion_claustro.turnos_autoridad.select_related("turno"):
            asignaciones = AsignacionAutoridad.objects.filter(mesa=mesa, turno=config.turno).exclude(estado=AsignacionAutoridad.Estado.RECHAZADA)
            titulares = asignaciones.filter(tipo=AsignacionAutoridad.Tipo.TITULAR).count()
            suplentes = 0
            sin_cubrir.extend([(mesa, config.turno)] * max(0, config.titulares_por_mesa - titulares))
            filas.append({
                "mesa": mesa, "turno": config.turno,
                "titulares": titulares, "maximo_titulares": config.titulares_por_mesa,
                "minimo_titulares": config.minimo_titulares_por_mesa,
                "suplentes": suplentes, "maximo_suplentes": config.suplentes_por_mesa,
                "suplentes_faltantes": max(0, config.suplentes_por_mesa - suplentes),
                "cubierta": titulares >= config.titulares_por_mesa,
            })
    return filas, sin_cubrir


@login_required
def descargar_plantilla_autoridades(request, eleccion_id, claustro_id=None):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_gestionar_autoridades(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
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
    if not puede_gestionar_autoridades(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
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
def confirmar_autoridades_definitivas(request, eleccion_id):
    if request.method != "POST":
        raise Http404()
    from apps.autoridades.confirmacion import confirmar_autoridades
    from django.core.exceptions import PermissionDenied
    try:
        cantidad = confirmar_autoridades(eleccion_id, request.user, parse_date(request.POST.get("fecha_limite", "")))
    except PermissionDenied:
        return HttpResponseForbidden("No tiene permiso para confirmar autoridades.")
    except (ValidationError, ValueError) as error:
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else str(error))
    else:
        messages.success(request, f"Autoridades confirmadas. Se registraron {cantidad} convocatorias.")
    return redirect("gestionar-autoridades", eleccion_id=eleccion_id)


@login_required
def previsualizar_recalculo_mesas(request, eleccion_id):
    from apps.autoridades.nomina import _huella
    from apps.padron.services import calcular_mesas_automaticas_eleccion
    from apps.mesas.models import Mesa

    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_gestionar_autoridades(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para recalcular las mesas.")

    def huellas(actual):
        return [_huella(c) for c in actual.elecciones_claustro.order_by("pk")]

    if request.method == "POST":
        try:
            datos = signing.loads(request.POST.get("propuesta", ""), salt="recalculo-mesas", max_age=1800)
            with transaction.atomic():
                actual = Eleccion.objects.select_for_update().get(pk=eleccion_id)
                if not puede_gestionar_autoridades(request.user, actual):
                    return HttpResponseForbidden("La elección ya no admite cambios.")
                if datos != {"eleccion": actual.pk, "huellas": huellas(actual)}:
                    raise ValueError("Los datos cambiaron; revisá una nueva propuesta antes de confirmar.")
                resultado = calcular_mesas_automaticas_eleccion(actual, usuario=request.user, request=request,
                                                               recalcular_sedes=False, conservar_mesas=True, confirmar_afectadas=True)
        except (signing.BadSignature, ValueError) as error:
            messages.error(request, str(error) if isinstance(error, ValueError) else "La propuesta venció; calculala nuevamente.")
            return redirect("previsualizar-recalculo-mesas", eleccion_id=eleccion_id)
        messages.success(request, f"Mesas recalculadas. Designaciones provisorias que quedaron vacantes: {resultado.get('autoridades_vacantes', 0)}.")
        return redirect("gestionar-autoridades", eleccion_id=eleccion_id)

    try:
        estado = {"eleccion": eleccion.pk, "huellas": huellas(eleccion)}
        with transaction.atomic():
            resultado = calcular_mesas_automaticas_eleccion(eleccion, usuario=request.user, recalcular_sedes=False, conservar_mesas=True, confirmar_afectadas=True)
            ids_registros = [movimiento["registro"] for movimiento in resultado.get("movimientos", [])]
            nombres = {r.pk: r.elector.nombre_completo for r in RegistroPadron.objects.filter(pk__in=ids_registros).select_related("elector")}
            numeros = {mesa.pk: mesa.codigo for mesa in Mesa.objects.filter(eleccion=eleccion).select_related("eleccion_claustro_departamento__departamento")}
            movimientos = [{"elector": nombres.get(m["registro"], ""), "origen": numeros.get(m["origen"], "Sin mesa"),
                            "destino": numeros.get(m["destino"], "Mesa nueva")} for m in resultado.get("movimientos", [])]
            transaction.set_rollback(True)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("gestionar-autoridades", eleccion_id=eleccion_id)
    return render(request, "autoridades/previsualizar_recalculo_mesas.html", {
        "eleccion": eleccion, "resultado": resultado, "movimientos": movimientos,
        "propuesta": signing.dumps(estado, salt="recalculo-mesas"),
    })


@login_required
def revisar_retorno_votacion(request, asignacion_id):
    from apps.auditoria.services import registrar_evento
    from apps.autoridades.nomina import _huella
    from apps.autoridades.retorno_votacion import planificar_retorno
    from apps.justificativos.models import JustificativoAusencia
    from apps.mesas.models import AsignacionMesa
    from apps.padron.models import AsignacionSedePadron
    from apps.usuarios.permisos import puede_administrar_elecciones

    asignacion = get_object_or_404(AsignacionAutoridad.objects.select_related(
        "registro_padron__eleccion", "mesa__eleccion_claustro_departamento__eleccion_claustro", "mesa_votacion_original__sede",
    ), pk=asignacion_id)
    eleccion = asignacion.registro_padron.eleccion
    claustro = asignacion.mesa.eleccion_claustro_departamento.eleccion_claustro
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para revisar el retorno.")
    if (eleccion.estado != Eleccion.Estado.PUBLICADA or not eleccion.autoridades_confirmadas_en
            or asignacion.estado != AsignacionAutoridad.Estado.RECHAZADA
            or not JustificativoAusencia.objects.filter(registro_padron=asignacion.registro_padron, ausencia="autoridad", estado="aprobado").exists()):
        return HttpResponseForbidden("El retorno solo puede revisarse tras aprobar una ausencia de autoridades confirmadas.")
    destino_url = reverse("gestionar-autoridades-claustro", args=(eleccion.pk, claustro.pk))
    try:
        if request.method == "POST":
            datos = signing.loads(request.POST.get("propuesta", ""), salt="retorno-votacion", max_age=1800)
            with transaction.atomic():
                eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
                if eleccion.estado != Eleccion.Estado.PUBLICADA or not eleccion.autoridades_confirmadas_en:
                    raise ValidationError("La elección ya no admite cambios de mesa.")
                asignacion = AsignacionAutoridad.objects.select_for_update(of=("self",)).select_related(
                    "registro_padron__eleccion", "mesa_votacion_original__sede", "mesa__eleccion_claustro_departamento__eleccion_claustro",
                ).get(pk=asignacion_id)
                if (asignacion.estado != AsignacionAutoridad.Estado.RECHAZADA
                        or not JustificativoAusencia.objects.filter(registro_padron=asignacion.registro_padron, ausencia="autoridad", estado="aprobado").exists()
                        or datos != {"asignacion": asignacion_id, "huella": _huella(claustro)}):
                    raise ValidationError("Los datos cambiaron; revisá una nueva propuesta.")
                movimientos = planificar_retorno(asignacion)
                filas = {
                    fila.registro_padron_id: fila
                    for fila in AsignacionMesa.objects.select_for_update().filter(
                        registro_padron_id__in=[movimiento["registro"] for movimiento in movimientos],
                    ).select_related("mesa", "registro_padron__eleccion_claustro_departamento")
                }
                destinos = Mesa.objects.in_bulk([movimiento["mesa_id"] for movimiento in movimientos])
                if len(filas) != len(movimientos) or any(m["mesa_id"] not in destinos for m in movimientos):
                    raise ValidationError("El padrón cambió; revisá una nueva propuesta.")
                movimientos = sorted(movimientos, key=lambda m: not filas[m["registro"]].registro_padron.es_principal)
                for movimiento in movimientos:
                    fila = filas[movimiento["registro"]]
                    mesa = destinos[movimiento["mesa_id"]]
                    if fila.mesa.sede_id != mesa.sede_id:
                        sede, _ = AsignacionSedePadron.objects.get_or_create(
                            registro_padron=fila.registro_padron,
                            defaults={"sede_id": mesa.sede_id, "estado": AsignacionSedePadron.Estado.ASIGNADA},
                        )
                        sede.sede_id = mesa.sede_id
                        sede.estado = AsignacionSedePadron.Estado.ASIGNADA
                        sede.regla_aplicada = None
                        sede.full_clean()
                        sede.save()
                    fila.mesa = mesa
                    fila.autoridad_al_final = False
                    fila.full_clean()
                    fila.save(update_fields=("mesa", "autoridad_al_final"))
                registrar_evento(accion="autoridades.restitucion_mesa_votacion", entidad="RegistroPadron", entidad_id=asignacion.registro_padron_id,
                                 eleccion=eleccion, usuario=request.user, request=request, datos_nuevos={"movimientos": movimientos})
            messages.success(request, f"Se confirmó el regreso y se actualizaron {len(movimientos)} asignaciones de mesa.")
            return redirect(destino_url)
        movimientos = planificar_retorno(asignacion)
        propuesta = signing.dumps({"asignacion": asignacion_id, "huella": _huella(claustro)}, salt="retorno-votacion")
    except (ValidationError, signing.BadSignature) as error:
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "La propuesta venció; revisala nuevamente.")
        return redirect(destino_url)
    return render(request, "autoridades/revisar_retorno_votacion.html", {"eleccion": eleccion, "asignacion": asignacion,
                                                                          "movimientos": movimientos, "propuesta": propuesta})


@login_required
@transaction.atomic
def gestionar_autoridades_claustro(request, eleccion_id, claustro_id):
    eleccion_claustro = get_object_or_404(
        EleccionClaustro.objects.select_related("eleccion", "claustro"),
        pk=claustro_id,
        eleccion_id=eleccion_id,
    )
    eleccion = eleccion_claustro.eleccion
    if request.method == "POST":
        eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
        eleccion_claustro.eleccion = eleccion
    if not puede_gestionar_autoridades(request.user, eleccion, solo_consulta=request.method in ("GET", "HEAD")):
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
        propuesta = request.session.get(clave_nomina, {})
        ImportacionNominaAutoridades.objects.filter(
            pk=propuesta.get("importacion_id"), eleccion_claustro=eleccion_claustro,
            usuario=request.user, estado=ImportacionNominaAutoridades.Estado.PREVISUALIZADA,
        ).update(estado=ImportacionNominaAutoridades.Estado.CANCELADA)
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
                alternativa = request.POST.get("alternativa")
                resumen = confirmar_nomina(eleccion_claustro, request.user, propuesta, alternativa=alternativa)
            except ValidationError as error:
                messages.error(request, "No se aplicó la nómina: " + " ".join(error.messages))
                ImportacionNominaAutoridades.objects.filter(
                    pk=propuesta.get("importacion_id"), eleccion_claustro=eleccion_claustro,
                    usuario=request.user, estado=ImportacionNominaAutoridades.Estado.PREVISUALIZADA,
                ).update(estado=ImportacionNominaAutoridades.Estado.RECHAZADA, errores=error.messages)
            else:
                messages.success(request, f"Se asignaron {resumen['titulares']} titulares; {resumen['sin_asignar']} personas quedaron sin asignar.")
                from apps.autoridades.nomina import previsualizar_nomina
                try:
                    elegida = next((opcion for opcion in propuesta.get("alternativas", []) if opcion.get("codigo") == alternativa), None)
                    datos_actuales = {**(elegida["datos"] if elegida else propuesta["datos"]), "registros": []}
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
                f"{resumen['titulares_faltantes']} titulares.",
            )
            if resumen["titulares_faltantes"] or resumen["suplentes_faltantes"]:
                messages.warning(request, "Se alcanzó la mayor cobertura posible: no hay una combinación compatible que cubra más cupos respetando la prioridad de titulares, el padrón y los turnos actuales.")
        except ValidationError as error:
            messages.error(request, error.messages[0])
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if request.method == "POST" and "eliminar-asignaciones" in request.POST:
        if request.POST.get("confirmar-eliminacion") != "1":
            messages.error(request, "Confirmá la eliminación de todas las asignaciones y candidaturas de autoridad antes de continuar.")
        else:
            from apps.autoridades.distribucion import eliminar_asignaciones
            try:
                cantidad = eliminar_asignaciones(eleccion_claustro, request.user)
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                request.session.pop(clave_propuesta, None)
                request.session.pop(clave_nomina, None)
                request.session.pop(clave_comparacion, None)
                messages.success(request, f"Se eliminaron {cantidad} asignaciones y se vació la nómina de posibles autoridades de este claustro. El padrón y las mesas se conservaron.")
        return redirect("gestionar-autoridades-claustro", eleccion_id=eleccion.id, claustro_id=claustro_id)
    if aplicar_modo and formulario_modo.is_valid():
        modo_elegido = formulario_modo.cleaned_data["modo"]
        if modo_elegido == "nomina":
            if actualizar_nomina and modo_anterior != "nomina":
                formulario_nomina.add_error("archivo", "Cargá el archivo de nómina para iniciar la nómina común.")
            elif formulario_nomina.is_valid():
                from apps.autoridades.nomina import identificar_nomina, previsualizar_nomina
                archivo = formulario_nomina.cleaned_data["archivo"]
                importacion = None
                contenido = archivo.read() if archivo else None
                if archivo:
                    anterior = request.session.get(clave_nomina, {})
                    ImportacionNominaAutoridades.objects.filter(
                        pk=anterior.get("importacion_id"), eleccion_claustro=eleccion_claustro,
                        usuario=request.user, estado=ImportacionNominaAutoridades.Estado.PREVISUALIZADA,
                    ).update(estado=ImportacionNominaAutoridades.Estado.CANCELADA)
                    request.session.pop(clave_nomina, None)
                    archivo.seek(0)
                    importacion = ImportacionNominaAutoridades.objects.create(
                        eleccion_claustro=eleccion_claustro, usuario=request.user,
                        archivo=archivo, nombre_archivo=archivo.name[:255],
                        huella_archivo=hashlib.sha256(contenido).hexdigest(),
                    )
                try:
                    registros = identificar_nomina(eleccion_claustro, contenido, archivo.name) if archivo else []
                    datos = {"registros": registros, "mesa": formulario_modo.cleaned_data["reacomodar_titulares"],
                             "votar_mesa": formulario_modo.cleaned_data["permitir_mesa_distinta"],
                             "sede": formulario_modo.cleaned_data["permitir_cambio_sede"]}
                    propuesta = previsualizar_nomina(eleccion_claustro, request.user, datos)
                    if importacion:
                        importacion.cantidad_validas = RegistroPadron.objects.filter(
                            pk__in=registros,
                        ).values("elector_id").distinct().count()
                        importacion.save(update_fields=("cantidad_validas",))
                        propuesta["importacion_id"] = importacion.pk
                    request.session[clave_nomina] = propuesta
                except ValidationError as error:
                    if importacion:
                        importacion.estado = ImportacionNominaAutoridades.Estado.RECHAZADA
                        importacion.errores = error.messages
                        importacion.save(update_fields=("estado", "errores"))
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
                            f"{resumen['titulares_faltantes']} titulares."
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
            messages.success(request, f"Distribución aplicada: {resumen['asignadas']} autoridades. Faltan {resumen['titulares_faltantes']} titulares; completá los cupos pendientes.")
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
                minimo = int(request.POST.get(f"minimo_titulares_{turno.id}", existente.minimo_titulares_por_mesa if existente else 1))
                suplentes = int(request.POST.get(f"suplentes_{turno.id}", 0))
            except (TypeError, ValueError):
                titulares, minimo, suplentes = 0, 0, -1
            if not 1 <= minimo <= titulares <= 32767 or suplentes != 0:
                formulario_turnos.add_error(None, "El mínimo debe ser al menos 1 y no superar el máximo de titulares; no se permiten suplentes.")
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
            limites.append((turno, titulares, minimo, suplentes))
        if formulario_turnos.errors:
            messages.error(request, "Revisá los cupos configurados para cada turno.")
        else:
            try:
                with transaction.atomic():
                    formulario_turnos.guardar()
                    for turno, titulares, minimo, suplentes in limites:
                        config = eleccion_claustro.turnos_autoridad.get(turno=turno)
                        config.titulares_por_mesa = titulares
                        config.minimo_titulares_por_mesa = minimo
                        config.suplentes_por_mesa = suplentes
                        config.save(update_fields=("titulares_por_mesa", "minimo_titulares_por_mesa", "suplentes_por_mesa"))
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
    vacantes_pendientes = {(mesa.pk, turno.pk) for mesa, turno in sin_cubrir}
    for asignacion in autoridades.filter(mesa__in=pagina_mesas.object_list).order_by(
        "mesa__numero", "turno__hora_inicio",
        Case(When(tipo=AsignacionAutoridad.Tipo.TITULAR, then=Value(0)), default=Value(1), output_field=IntegerField()),
        "orden_suplencia", "registro_padron__elector__apellido", "registro_padron__elector__nombre",
    ):
        if asignacion.estado == AsignacionAutoridad.Estado.RECHAZADA and asignacion.mesa_votacion_original_id:
            from apps.mesas.models import AsignacionMesa
            mesa_votacion = AsignacionMesa.objects.filter(registro_padron=asignacion.registro_padron).values_list("mesa_id", flat=True).first()
            asignacion.retorno_votacion_pendiente = bool(mesa_votacion and mesa_votacion != asignacion.mesa_votacion_original_id)
        if (asignacion.estado == AsignacionAutoridad.Estado.RECHAZADA and not asignacion.reemplazo_confirmado_en and eleccion.estado == Eleccion.Estado.PUBLICADA
                and (asignacion.mesa_id, asignacion.turno_id) in vacantes_pendientes):
            from apps.autoridades.traslados_vacantes import candidatos_para_vacante
            from apps.justificativos.models import JustificativoAusencia
            asignacion.ausencia_aprobada = JustificativoAusencia.objects.filter(
                registro_padron=asignacion.registro_padron, ausencia="autoridad", estado="aprobado",
            ).exists()
            if asignacion.ausencia_aprobada:
                asignacion.candidatos_vacante = list(candidatos_para_vacante(asignacion))
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
            "minimo_titulares_por_mesa": configuracion.minimo_titulares_por_mesa if configuracion else 1,
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
            "importaciones_nomina": eleccion_claustro.importaciones_autoridades.select_related("usuario"),
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
def descargar_importacion_nomina(request, eleccion_id, claustro_id, importacion_id):
    importacion = get_object_or_404(
        ImportacionNominaAutoridades.objects.select_related("eleccion_claustro__eleccion"),
        pk=importacion_id, eleccion_claustro_id=claustro_id,
        eleccion_claustro__eleccion_id=eleccion_id,
    )
    if not puede_gestionar_autoridades(request.user, importacion.eleccion_claustro.eleccion, solo_consulta=True):
        return HttpResponseForbidden("No tiene permiso para consultar esta importación.")
    return FileResponse(importacion.archivo.open("rb"), as_attachment=True, filename=importacion.nombre_archivo)


@login_required
def seleccionar_autoridades_mesa(request, eleccion_id, claustro_id, mesa_id):
    from apps.autoridades.seleccion_manual import asignar_manualmente, quitar_designacion
    mesa = get_object_or_404(Mesa.objects.select_related("eleccion", "eleccion_claustro_departamento__eleccion_claustro", "sede"), pk=mesa_id, eleccion_id=eleccion_id, eleccion_claustro_departamento__eleccion_claustro_id=claustro_id)
    claustro = mesa.eleccion_claustro_departamento.eleccion_claustro
    if not puede_gestionar_autoridades(request.user, mesa.eleccion):
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
        asignaciones = asignaciones.filter(registro_padron__elector=elector).filter(
            Q(registro_padron__eleccion__autoridades_confirmadas_en__isnull=False)
            | Q(registro_padron__eleccion__estado=Eleccion.Estado.FINALIZADA)
        )
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
    if asignacion.estado == AsignacionAutoridad.Estado.RECHAZADA:
        messages.info(request, "La asignación ya figura como rechazada.")
        return redirect("mis-asignaciones-autoridad")
    messages.info(request, "Para informar que no podrás ejercer, presentá un justificativo de ausencia como autoridad.")
    from django.urls import reverse
    return redirect(f"{reverse('mis-justificativos')}?ausencia=autoridad")


@login_required
def confirmar_traslado_vacante(request, asignacion_id):
    from apps.autoridades.traslados_vacantes import confirmar_traslado_por_vacante
    from django.core.exceptions import PermissionDenied
    if request.method != "POST":
        raise Http404()
    ausente = get_object_or_404(
        AsignacionAutoridad.objects.select_related("registro_padron__eleccion", "mesa__eleccion_claustro_departamento"),
        pk=asignacion_id,
    )
    try:
        candidato_id = int(request.POST.get("candidato_id", ""))
        confirmar_traslado_por_vacante(ausente, candidato_id, request.user)
    except (TypeError, ValueError):
        messages.error(request, "Elegí una autoridad de la propuesta.")
    except PermissionDenied:
        return HttpResponseForbidden("No tiene permiso para confirmar el traslado.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "Se confirmó el traslado y se generó la notificación. La mesa de votación no cambió.")
    return redirect("gestionar-autoridades-claustro", eleccion_id=ausente.registro_padron.eleccion_id,
                    claustro_id=ausente.mesa.eleccion_claustro_departamento.eleccion_claustro_id)


@login_required
def confirmar_reemplazo_autoridad(request, asignacion_id):
    if request.method != "POST":
        raise Http404()
    return HttpResponseForbidden("Las vacantes de autoridades permanecen sin cubrir; no se designan suplentes.")


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
