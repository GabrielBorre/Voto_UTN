"""Ejecuta una aprobación y su recálculo dentro de la transacción llamadora."""
from django.db import transaction
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import RegistroPadron
from apps.padron.services import calcular_mesas_automaticas_eleccion, resolver_solicitudes_pendientes


@transaction.atomic
def aplicar_cambios_con_recalculo(eleccion, usuario, datos):
    mesas_antes = {mesa.pk: mesa.codigo for mesa in Mesa.objects.filter(eleccion=eleccion).select_related("eleccion_claustro_departamento__departamento")}
    filas_antes = dict(AsignacionMesa.objects.filter(registro_padron__eleccion=eleccion).values_list("registro_padron_id", "mesa_id"))
    resultado = resolver_solicitudes_pendientes(
        eleccion, usuario=usuario, accion=datos["accion"], observacion_resolucion=datos["observacion"],
        maximo_mesas_nuevas=datos["maximo"], solicitudes_ids=datos["ids"],
    )
    recalculo = {"detalle_autoridades_vacantes": []}
    if resultado["aprobadas"]:
        recalculo = calcular_mesas_automaticas_eleccion(eleccion, usuario=usuario, recalcular_sedes=False,
                                                        conservar_mesas=True, confirmar_afectadas=True)
    mesas_despues = {mesa.pk: mesa.codigo for mesa in Mesa.objects.filter(eleccion=eleccion).select_related("eleccion_claustro_departamento__departamento")}
    agregadas = sorted(set(mesas_despues) - set(mesas_antes))
    quitadas = sorted(set(mesas_antes) - set(mesas_despues))
    if datos["accion"] == "aprobar_sin_agregar_mesas" and agregadas:
        raise ValueError("El recálculo requiere agregar mesas; elegí otra modalidad de resolución.")
    if datos["accion"] == "aprobar_con_maximo_mesas" and len(agregadas) > datos["maximo"]:
        raise ValueError("El recálculo supera el límite de mesas nuevas indicado.")
    filas_despues = dict(AsignacionMesa.objects.filter(registro_padron__eleccion=eleccion).values_list("registro_padron_id", "mesa_id"))
    cambios = [(r, anterior, filas_despues.get(r)) for r, anterior in filas_antes.items() if filas_despues.get(r) != anterior]
    cambios.extend((r, None, mesa) for r, mesa in filas_despues.items() if r not in filas_antes)
    nombres = {r.pk: r.elector.nombre_completo for r in RegistroPadron.objects.filter(pk__in=[c[0] for c in cambios]).select_related("elector")}
    return {"resultado": resultado, "autoridades": recalculo.get("detalle_autoridades_vacantes", []),
            "agregadas": [mesas_despues[x] for x in agregadas], "quitadas": [mesas_antes[x] for x in quitadas],
            "movimientos": [{"elector": nombres.get(r, ""), "origen": mesas_antes.get(a, "Sin mesa"),
                             "destino": mesas_despues.get(d, "Sin mesa")} for r, a, d in cambios]}
