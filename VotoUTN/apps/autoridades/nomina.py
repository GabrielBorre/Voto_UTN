"""Carga de nómina y distribución automática en una única transacción."""
import hashlib
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.autoridades.distribucion import _auditar, bloquear_edicion, configuracion_actual, distribuir
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.usuarios.permisos import puede_configurar_eleccion


def resumen_actual(claustro):
    nomina = CandidaturaAutoridad.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
    )
    asignaciones = AsignacionAutoridad.objects.filter(
        registro_padron_id__in=nomina.values("registro_padron_id"), estado="asignada",
    )
    titulares = asignaciones.filter(tipo="titular").count()
    suplentes = asignaciones.filter(tipo="suplente").count()
    total = nomina.count()
    return {"titulares": titulares, "suplentes": suplentes,
            "total": total, "sin_asignar": total - titulares - suplentes}


def _guardar_opciones(claustro, usuario, formulario):
    if not puede_configurar_eleccion(usuario, claustro.eleccion):
        raise PermissionDenied("No tiene permiso para gestionar autoridades.")
    bloquear_edicion(claustro)
    if formulario.cleaned_data["modo"] != "nomina":
        raise ValidationError("La operación requiere el modo nómina común.")
    opciones = formulario.save()
    _auditar(claustro, usuario, "autoridades.configuracion", {
        "modo": opciones.modo, "permitir_cambio_sede": opciones.permitir_cambio_sede,
        "reacomodar_titulares": opciones.reacomodar_titulares,
        "permitir_mesa_distinta": opciones.permitir_mesa_distinta,
    })


def identificar_nomina(claustro, contenido, nombre):
    """Valida el archivo y devuelve solo identificadores internos para la sesión."""
    from apps.autoridades.services import validar_csv_autoridades
    from apps.padron.models import RegistroPadron
    filas, errores = validar_csv_autoridades(contenido, claustro, nombre)
    if errores:
        raise ValidationError([f"Fila {n}: {mensaje}" if n else mensaje for n, mensaje in errores[:10]])
    ids = []
    for fila in filas:
        consulta = RegistroPadron.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro, activo=True)
        if fila["documento"]:
            consulta = consulta.filter(elector__tipo_documento__iexact=fila["tipo_documento"], elector__dni=fila["documento"])
        if fila["legajo"]:
            consulta = consulta.filter(elector__legajo=fila["legajo"])
        try:
            ids.append(consulta.get().pk)
        except (RegistroPadron.DoesNotExist, RegistroPadron.MultipleObjectsReturned) as error:
            raise ValidationError("El padrón cambió durante la validación. Volvé a cargar el archivo de nómina.") from error
    if len(ids) != len(set(ids)):
        raise ValidationError("Una persona aparece más de una vez en el archivo.")
    return ids


def _huella(claustro):
    """Identifica datos que pueden alterar el cálculo mientras se revisa."""
    from apps.mesas.models import AsignacionMesa, Mesa
    from apps.padron.models import AsignacionSedePadron, RegistroPadron, SolicitudCambioSede
    from apps.elecciones.models import EleccionClaustroDepartamentoSede
    from apps.partidos.models import Candidato
    from apps.autoridades.models import ConfiguracionAutoridades
    from apps.usuarios.models import AsignacionRol, PerfilUsuario
    mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro)
    registros = RegistroPadron.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro)
    estado = {
        "eleccion": list(type(claustro.eleccion).objects.filter(pk=claustro.eleccion_id).values_list("estado", flat=True)),
        "maximo": list(type(claustro).objects.filter(pk=claustro.pk).values_list("maximo_votantes_por_mesa", flat=True)),
        "mesas": list(mesas.order_by("pk").values_list("pk", "numero", "sede_id", "sede__nombre", "sede__activa", "eleccion_claustro_departamento_id", "eleccion_claustro_departamento__departamento__codigo", "eleccion_claustro_departamento__departamento__nombre", "generada_automaticamente", "estado_escaneo")),
        "registros": list(registros.order_by("pk").values_list("pk", "activo", "sede_id", "turno_cursada_id", "turno_cursada__hora_inicio", "turno_cursada__hora_fin", "qr_generado_en", "numero_mesa_qr", "elector__apellido", "elector__nombre", "elector__tipo_documento", "elector__dni", "elector__legajo")),
        "padron": list(AsignacionMesa.objects.filter(registro_padron__in=registros).order_by("registro_padron_id").values_list("registro_padron_id", "mesa_id", "autoridad_al_final")),
        "sedes": list(AsignacionSedePadron.objects.filter(registro_padron__in=registros).order_by("registro_padron_id").values_list("registro_padron_id", "sede_id", "estado", "regla_aplicada_id")),
        "autoridades": list(AsignacionAutoridad.objects.filter(mesa__in=mesas).order_by("pk").values_list("pk", "registro_padron_id", "mesa_id", "turno_id", "tipo", "orden_suplencia", "estado", "respondida_en")),
        "nomina": list(CandidaturaAutoridad.objects.filter(registro_padron__in=registros).order_by("pk").values_list("pk", "registro_padron_id", "excluida", "mesa_manual_id", "turno_manual_id", "tipo_manual", "orden_manual", "mesa_traslado_id", "turno_traslado_id")),
        "turnos": list(claustro.turnos_autoridad.order_by("turno_id").values_list("turno_id", "turno__hora_inicio", "turno__hora_fin", "titulares_por_mesa", "suplentes_por_mesa")),
        "sedes_habilitadas": list(EleccionClaustroDepartamentoSede.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro).order_by("pk").values_list("pk", "eleccion_claustro_departamento_id", "sede_id", "sede__activa")),
        "solicitudes": list(SolicitudCambioSede.objects.filter(registro_padron__in=registros).order_by("pk").values_list("pk", "registro_padron_id", "estado", "sede_origen_id", "sede_destino_id")),
        "perfiles": list(PerfilUsuario.objects.filter(elector__registros_padron__in=registros).order_by("pk").values_list("pk", "elector_id", "usuario_id", "activo").distinct()),
        "roles": list(AsignacionRol.objects.filter(mesa__in=mesas).order_by("pk").values_list("pk", "usuario_id", "mesa_id", "sede_id", "rol", "activo")),
        "opciones": list(ConfiguracionAutoridades.objects.filter(eleccion_claustro=claustro).values_list("modo", "permitir_cambio_sede", "reacomodar_titulares", "permitir_mesa_distinta")),
        "candidatos": list(Candidato.objects.filter(lista__participacion__eleccion=claustro.eleccion, activo=True).order_by("pk").values_list("pk", "elector_id", "dni")),
    }
    return hashlib.sha256(json.dumps(estado, sort_keys=True, default=str).encode()).hexdigest()


def _estado_resultado(claustro):
    from apps.mesas.models import AsignacionMesa, Mesa
    mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro)
    return {
        "mesas": list(mesas.order_by("numero").values_list("numero", "eleccion_claustro_departamento_id", "sede_id")),
        "padron": list(AsignacionMesa.objects.filter(mesa__in=mesas).order_by("registro_padron_id").values_list("registro_padron_id", "mesa__numero", "autoridad_al_final")),
        "autoridades": list(AsignacionAutoridad.objects.filter(mesa__in=mesas, estado="asignada").order_by("registro_padron_id").values_list("registro_padron_id", "mesa__numero", "turno_id", "tipo", "orden_suplencia")),
    }


def _ejecutar_propuesta(claustro, usuario, datos):
    from collections import Counter
    from apps.autoridades.distribucion import es_candidato_electoral
    from apps.autoridades.forms import FormularioConfiguracionAutoridades
    from apps.mesas.models import Mesa
    from apps.padron.models import RegistroPadron

    conservados = set(AsignacionAutoridad.objects.filter(mesa__eleccion_claustro_departamento__eleccion_claustro=claustro, estado="asignada").values_list("registro_padron_id", flat=True))
    formulario = FormularioConfiguracionAutoridades({
        "modo": "nomina", "permitir_cambio_sede": datos["sede"],
        "reacomodar_titulares": datos["mesa"], "permitir_mesa_distinta": datos.get("votar_mesa", False),
    }, instance=configuracion_actual(claustro))
    if not formulario.is_valid():
        raise ValidationError("La configuración de la nómina ya no es válida.")
    _guardar_opciones(claustro, usuario, formulario)
    registros = RegistroPadron.objects.filter(pk__in=datos["registros"], activo=True, eleccion_claustro_departamento__eleccion_claustro=claustro).select_related("elector")
    if registros.count() != len(datos["registros"]):
        raise ValidationError("La nómina cambió; volvé a cargar el archivo de nómina.")
    for registro in registros:
        if es_candidato_electoral(registro):
            raise ValidationError("Un candidato electoral no puede ser autoridad de mesa.")
        CandidaturaAutoridad.objects.get_or_create(registro_padron=registro, defaults={"cargada_por": usuario})

    cantidad_candidaturas = CandidaturaAutoridad.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
    ).count()
    actuales = list(Mesa.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro=claustro,
    ).values_list("numero", "eleccion_claustro_departamento_id", "sede_id"))
    for _ in range(cantidad_candidaturas + len(conservados) + 3):
        resultado = distribuir(claustro, usuario, aplicar_reacomodo=False)
        if not datos["mesa"]:
            break
        from apps.autoridades.reordenamiento_padron import aplicar_padrones, previsualizar_padrones
        titulares = dict(AsignacionAutoridad.objects.filter(
            mesa__eleccion_claustro_departamento__eleccion_claustro=claustro,
            estado="asignada", tipo="titular",
        ).values_list("registro_padron_id", "mesa_id"))
        propuesta = previsualizar_padrones(
            claustro, titulares=titulares, permitir_cambio_mesa=True,
            permitir_cambio_sede=datos["sede"], registros_conservados=conservados,
        )
        movimientos = aplicar_padrones(claustro, propuesta, titulares=titulares)
        if movimientos or propuesta["mesas_nuevas"] or propuesta["mesas_quitadas"]:
            _auditar(claustro, usuario, "autoridades.padron_reordenado", {
                "movimientos": movimientos, "mesas_nuevas": len(propuesta["mesas_nuevas"]),
                "mesas_quitadas": propuesta["mesas_quitadas"], "titulares": sorted(titulares),
            })
        if not movimientos and not propuesta["mesas_nuevas"] and not propuesta["mesas_quitadas"]:
            break
    else:
        raise ValidationError("No se pudo estabilizar el cálculo de mesas; no se aplicó ningún cambio.")

    final = _estado_resultado(claustro)
    despues = Counter((alcance, sede) for _, alcance, sede in final["mesas"])
    antes = Counter((alcance, sede) for _, alcance, sede in actuales)
    antes_detalle = {(numero, alcance, sede) for numero, alcance, sede in actuales}
    despues_detalle = {tuple(mesa) for mesa in final["mesas"]}
    from apps.elecciones.models import EleccionClaustroDepartamento
    from apps.parametros.models import Sede
    cambios = []
    for alcance_id, sede_id in sorted(set(antes) | set(despues), key=str):
        agregadas = sorted(numero for numero, alcance, sede in despues_detalle - antes_detalle if (alcance, sede) == (alcance_id, sede_id))
        quitadas = sorted(numero for numero, alcance, sede in antes_detalle - despues_detalle if (alcance, sede) == (alcance_id, sede_id))
        if agregadas or quitadas:
            alcance = EleccionClaustroDepartamento.objects.select_related("departamento").get(pk=alcance_id)
            sede = Sede.objects.filter(pk=sede_id).first()
            codigo = alcance.departamento.codigo if alcance.departamento_id else ""
            formatear = lambda numero: f"{codigo}-{numero:03d}" if codigo else f"{numero:03d}"
            cambios.append({"departamento": str(alcance.departamento or "Sin departamento"), "sede": str(sede or "Sin sede"), "antes": antes[(alcance_id, sede_id)], "despues": despues[(alcance_id, sede_id)], "agregadas": [formatear(n) for n in agregadas], "quitadas": [formatear(n) for n in quitadas]})
    resumen = resumen_actual(claustro)
    resumen.update({"titulares_faltantes": resultado["titulares_faltantes"], "suplentes_faltantes": resultado["suplentes_faltantes"], "cambios": cambios})
    huella = hashlib.sha256(json.dumps(final, sort_keys=True, default=str).encode()).hexdigest()
    return resumen, huella


def previsualizar_nomina(claustro, usuario, datos):
    if not puede_configurar_eleccion(usuario, claustro.eleccion):
        raise PermissionDenied("No tiene permiso para gestionar autoridades.")
    estado = _huella(claustro)
    def simular(opciones):
        with transaction.atomic():
            resultado = _ejecutar_propuesta(claustro, usuario, opciones)
            transaction.set_rollback(True)
        return resultado
    resumen, calculo = simular(datos)
    alternativas = []
    for nombre, mesa, votar_mesa, sede in (
        ("Solo su mesa", False, False, False),
        ("Votar en mesa distinta", False, True, False),
        ("Permitir cambio de mesa", True, False, False),
        ("Permitir cambio de mesa y sede", True, False, True),
    ):
        if (mesa, votar_mesa, sede) == (datos["mesa"], datos.get("votar_mesa", False), datos["sede"]):
            resultado = resumen
        else:
            try:
                resultado, _ = simular({**datos, "mesa": mesa, "votar_mesa": votar_mesa, "sede": sede})
            except ValidationError as error:
                alternativas.append({"nombre": nombre, "error": " ".join(error.messages)})
                continue
        alternativas.append({"nombre": nombre, "titulares": resultado["titulares"],
                             "suplentes": resultado["suplentes"], "sin_asignar": resultado["sin_asignar"],
                             "titulares_faltantes": resultado["titulares_faltantes"],
                             "suplentes_faltantes": resultado["suplentes_faltantes"]})
    return {"datos": datos, "estado": estado, "calculo": calculo, "resumen": resumen, "alternativas": alternativas}


@transaction.atomic
def confirmar_nomina(claustro, usuario, propuesta):
    if not puede_configurar_eleccion(usuario, claustro.eleccion):
        raise PermissionDenied("No tiene permiso para gestionar autoridades.")
    bloquear_edicion(claustro)
    if _huella(claustro) != propuesta["estado"]:
        raise ValidationError("Los datos cambiaron desde la previsualización. Volvé a calcularla.")
    resumen, calculo = _ejecutar_propuesta(claustro, usuario, propuesta["datos"])
    if calculo != propuesta["calculo"]:
        raise ValidationError("El resultado cambió desde la previsualización. Volvé a calcularla.")
    _auditar(claustro, usuario, "autoridades.nomina_confirmada", resumen)
    return resumen
