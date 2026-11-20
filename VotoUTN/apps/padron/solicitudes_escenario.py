"""Carga las solicitudes reproducibles compartidas por la publicación y el guion."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.elecciones.models import Eleccion
from apps.padron.forms import FormularioSolicitudCambioSede
from apps.padron.models import RegistroPadron, SolicitudCambioSede
from apps.padron.services import solicitudes_cambio_sede_habilitadas


RUTA_PLAN_PUBLICACION = Path(__file__).with_name("datos") / "solicitudes_demo_publicacion.json"
RUTA_PLAN_PUBLICACION_SIN_ADICIONALES = (
    RUTA_PLAN_PUBLICACION.with_name("solicitudes_demo_publicacion_sin_adicionales.json")
)


def leer_plan_publicacion(ruta=RUTA_PLAN_PUBLICACION):
    try:
        plan = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError("No se pudo cargar el plan de solicitudes de publicación.") from error
    documentos = {fila["dni"] for fila in plan["solicitudes"]}
    compartidos = plan["solicitantes_nomina_pequena"]
    if (plan["version"] != 1 or len(plan["solicitudes"]) != 19 or len(documentos) != 19
            or len(set(compartidos)) != 3 or not set(compartidos) <= documentos or "38999222" in documentos):
        raise ValidationError("El plan de publicación debe contener diecinueve solicitantes y tres compartidos por las nóminas.")
    return plan


def _registros_por_documento(eleccion, planes):
    registros = RegistroPadron.objects.filter(
        eleccion=eleccion, activo=True, elector__dni__in=[fila["dni"] for fila in planes],
    ).select_related(
        "elector", "asignacion_sede_padron__sede", "eleccion_claustro_departamento__departamento",
        "eleccion_claustro_departamento__eleccion_claustro__claustro",
    ).prefetch_related("eleccion_claustro_departamento__sedes_habilitadas__sede")
    por_documento = defaultdict(list)
    for registro in registros:
        por_documento[registro.elector.dni].append(registro)
    return por_documento


def padron_corresponde_al_plan(eleccion, plan):
    """Reconoce identidades y departamentos; no elige sustitutos de otro padrón."""
    por_documento = _registros_por_documento(eleccion, plan["solicitudes"])
    for fila in plan["solicitudes"]:
        registros = por_documento[fila["dni"]]
        principales = [registro for registro in registros if registro.es_principal]
        if len(principales) != 1:
            return False
        principal = principales[0]
        alcance = principal.eleccion_claustro_departamento
        if (principal.elector.legajo != fila["legajo"] or principal.elector.tipo_documento != fila["tipo_documento"]
                or alcance.eleccion_claustro.claustro.abreviatura != plan["claustro"]
                or not alcance.departamento_id or alcance.departamento.codigo != fila["departamento_principal"]):
            return False
        departamentos = {r.eleccion_claustro_departamento.departamento.codigo
                         if r.eleccion_claustro_departamento.departamento_id else "" for r in registros}
        if departamentos != set(fila["departamentos"]):
            return False
    return True


def seleccionar_solicitudes_publicacion(eleccion):
    if settings.INSTANCIA_DEMO == "2":
        return _seleccionar_solicitudes_publicacion(
            eleccion, cantidad_objetivo=30, departamento="K",
        ) + _seleccionar_solicitudes_publicacion(
            eleccion, cantidad_objetivo=20, departamento="I",
            sede_origen="Campus", sede_destino="Medrano",
        ) + _seleccionar_solicitudes_publicacion(
            eleccion, cantidad_objetivo=4, departamento="U",
            sede_origen="Campus", sede_destino="Medrano",
        )
    return _seleccionar_solicitudes_publicacion(eleccion)


def _seleccionar_solicitudes_publicacion(
    eleccion, *, cantidad_objetivo=30, departamento=None,
    sede_origen=None, sede_destino=None,
):
    from apps.autoridades.models import AsignacionAutoridad

    autoridades = AsignacionAutoridad.objects.filter(
        registro_padron__eleccion=eleccion,
    ).values("registro_padron__elector_id")
    registros = RegistroPadron.objects.filter(
        eleccion=eleccion, activo=True,
        eleccion_claustro_departamento__eleccion_claustro__claustro__abreviatura__iexact="EST",
    ).exclude(elector_id__in=autoridades).exclude(elector__dni="38999222").select_related(
        "elector", "asignacion_sede_padron__sede",
    ).prefetch_related("eleccion_claustro_departamento__sedes_habilitadas__sede").order_by("elector_id", "pk")
    solicitudes = SolicitudCambioSede.objects.filter(registro_padron__eleccion=eleccion)
    if departamento is not None:
        # Se filtran personas por su principal, conservando todos sus adicionales.
        personas_departamento = RegistroPadron.objects.filter(
            eleccion=eleccion, es_principal=True,
            eleccion_claustro_departamento__eleccion_claustro__claustro__abreviatura__iexact="EST",
            eleccion_claustro_departamento__departamento__codigo=departamento,
        ).values("elector_id")
        registros = registros.filter(elector_id__in=personas_departamento)
        solicitudes_cupo = solicitudes.filter(registro_padron__elector_id__in=personas_departamento)
        if sede_origen is not None:
            solicitudes_cupo = solicitudes_cupo.filter(sede_origen__nombre=sede_origen)
        if sede_destino is not None:
            solicitudes_cupo = solicitudes_cupo.filter(sede_destino__nombre=sede_destino)
        # Las resueltas siguen cubriendo el cupo aunque el elector ya se haya trasladado.
        cantidad_existentes = solicitudes_cupo.values("registro_padron__elector_id").distinct().count()
    por_persona = defaultdict(list)
    for registro in registros:
        por_persona[registro.elector_id].append(registro)
    existentes = set(solicitudes.filter(
        registro_padron__elector_id__in=por_persona,
    ).values_list("registro_padron__elector_id", flat=True))
    if departamento is None:
        cantidad_existentes = len(existentes)
    cantidad = max(0, cantidad_objetivo - cantidad_existentes)
    planes = []
    for elector_id, asociados in por_persona.items():
        if len(planes) == cantidad:
            break
        if elector_id in existentes or sum(r.es_principal for r in asociados) != 1:
            continue
        origenes, destinos = set(), None
        for registro in asociados:
            asignacion = getattr(registro, "asignacion_sede_padron", None)
            if registro.sede_id or registro.qr_generado_en or not asignacion or not asignacion.sede_id:
                break
            origenes.add(asignacion.sede.nombre)
            habilitadas = {
                s.sede.nombre for s in registro.eleccion_claustro_departamento.sedes_habilitadas.all()
                if s.sede.activa
            }
            destinos = habilitadas if destinos is None else destinos & habilitadas
        else:
            alternativas = destinos - origenes
            if sede_origen is not None and origenes != {sede_origen}:
                continue
            if sede_destino is not None:
                alternativas &= {sede_destino}
            if len(origenes) == 1 and alternativas:
                planes.append({
                    "dni": asociados[0].elector.dni,
                    "origen": next(iter(origenes)),
                    "destino": sorted(alternativas)[0],
                })
    return planes


@transaction.atomic
def crear_solicitudes_escenario(eleccion, planes):
    """Crea solo las faltantes; conserva resoluciones, mesas y autoridades."""
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if not solicitudes_cambio_sede_habilitadas(eleccion):
        raise ValidationError("Publicá la elección y habilitá el plazo de cambios de sede.")
    if not planes or len({fila["dni"] for fila in planes}) != len(planes):
        raise ValidationError("El escenario debe contener solicitantes distintos.")
    por_documento = _registros_por_documento(eleccion, planes)
    creadas, existentes = [], Counter()
    for fila in planes:
        asociados = por_documento[fila["dni"]]
        principales = [registro for registro in asociados if registro.es_principal]
        if len(principales) != 1:
            raise ValidationError("Cada solicitante debe tener un registro principal activo.")
        registro = principales[0]
        anterior = SolicitudCambioSede.objects.filter(
            registro_padron__eleccion=eleccion, registro_padron__elector=registro.elector,
        ).select_related("sede_destino").first()
        if anterior:
            if anterior.sede_destino.nombre != fila["destino"]:
                raise ValidationError("La solicitud existente tiene otro destino.")
            existentes[anterior.estado] += 1
            continue
        for asociado in asociados:
            asignacion = getattr(asociado, "asignacion_sede_padron", None)
            destinos = [s.sede for s in asociado.eleccion_claustro_departamento.sedes_habilitadas.all()
                        if s.sede.activa and s.sede.nombre == fila["destino"]]
            if (asociado.sede_id or asociado.qr_generado_en or not asignacion or not asignacion.sede_id
                    or asignacion.sede.nombre != fila["origen"] or len(destinos) != 1):
                raise ValidationError("El padrón no permite el traslado conjunto: revisá actividad, QR y sedes habilitadas.")
            if asociado.pk == registro.pk:
                destino_principal = destinos[0]
        formulario = FormularioSolicitudCambioSede(
            {"sede_destino": destino_principal.pk, "observacion": "Solicitud sintética de escenario electoral."},
            registro_padron=registro,
        )
        if not formulario.is_valid():
            raise ValidationError("No se pudo validar una solicitud del escenario.")
        creadas.append(formulario.save().pk)
    return {"creadas": creadas, "existentes_por_estado": dict(existentes)}
