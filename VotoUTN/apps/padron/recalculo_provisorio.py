"""Recalcula mesas existentes sin sustituir identidades de mesa."""
from collections import defaultdict
from math import ceil

from django.db.models import Max
from django.db.models.deletion import ProtectedError

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades
from apps.auditoria.services import registrar_evento
from apps.mesas.models import AsignacionMesa, Mesa
from apps.usuarios.models import AsignacionRol, PerfilUsuario


def recalcular_con_autoridades(eleccion, grupos, *, usuario=None, request=None, confirmar_afectadas=False):
    """Aplica dentro de la transacción del cálculo general; informa vacantes.

    Conserva las mesas necesarias, crea las adicionales y quita las sobrantes
    únicamente cuando sus referencias provisorias pueden resolverse sin riesgo.
    """
    mesas_actuales = list(Mesa.objects.filter(eleccion=eleccion, generada_automaticamente=True).order_by("numero", "pk"))
    if AsignacionMesa.objects.filter(mesa__eleccion=eleccion, registro_padron__activo=False).exists():
        raise ValueError("Hay electores inactivos con mesa asignada; revisalos antes de recalcular.")
    if any(m.estado_escaneo != Mesa.EstadoEscaneo.PENDIENTE for m in mesas_actuales):
        raise ValueError("No se pueden recalcular mesas con el escaneo iniciado.")
    autoridades = list(AsignacionAutoridad.objects.filter(mesa__eleccion=eleccion).select_related("registro_padron__elector", "candidatura", "mesa", "turno"))
    if any(a.respondida_en or a.estado != AsignacionAutoridad.Estado.ASIGNADA for a in autoridades):
        raise ValueError("Hay respuestas de autoridades; no se puede recalcular la distribución provisoria.")
    por_grupo = defaultdict(list)
    for mesa in mesas_actuales:
        por_grupo[(mesa.eleccion_claustro_departamento_id, mesa.sede_id, mesa.es_especial)].append(mesa)
    claves_grupos = {(alcance.pk, sede.pk, especial) for _claustro, alcance, sede, especial in grupos}
    mesas_sin_electores = [mesa for clave, mesas in por_grupo.items() if clave not in claves_grupos for mesa in mesas]
    ids_sin_electores = {mesa.pk for mesa in mesas_sin_electores}
    anterior = {a.registro_padron_id: a for a in AsignacionMesa.objects.filter(registro_padron__eleccion=eleccion).select_related("mesa")}
    siguiente = (Mesa.objects.filter(eleccion=eleccion).aggregate(valor=Max("numero"))["valor"] or 0) + 1
    nuevos_destinos = {}
    resumen = defaultdict(lambda: {"electores": 0, "mesas": 0})
    creadas = []
    for (claustro, alcance, sede, es_especial), registros in grupos.items():
        existentes = por_grupo[(alcance.pk, sede.pk, es_especial)]
        maximo = claustro.maximo_votantes_por_mesa
        requeridas = ceil(len(registros) / maximo)
        if len(existentes) > requeridas:
            sobrantes = existentes[requeridas:]
            mesas_sin_electores.extend(sobrantes)
            ids_sin_electores.update(m.pk for m in sobrantes)
            existentes = existentes[:requeridas]
        while len(existentes) < requeridas:
            mesa = Mesa.objects.create(eleccion=eleccion, numero=siguiente, eleccion_claustro_departamento=alcance,
                                       sede=sede, generada_automaticamente=True, es_especial=es_especial)
            siguiente += 1
            existentes.append(mesa)
            creadas.append(mesa.pk)
        if requeridas == ceil(len(registros) / maximo):
            from apps.padron.services import _distribucion_electores_por_mesa
            cantidades = _distribucion_electores_por_mesa(len(registros), maximo)
        else:
            base, resto = divmod(len(registros), requeridas)
            cantidades = [base + int(indice < resto) for indice in range(requeridas)]
        inicio = 0
        for mesa, cantidad in zip(existentes, cantidades):
            for registro in registros[inicio:inicio + cantidad]:
                nuevos_destinos[registro.pk] = mesa
            inicio += cantidad
        resumen[claustro.claustro.nombre]["mesas"] += len(existentes)
        resumen[claustro.claustro.nombre]["electores"] += len(registros)
    detalle_quitadas = [mesa.codigo for mesa in mesas_sin_electores]
    if Mesa.objects.filter(pk__in=ids_sin_electores, participaciones__isnull=False).exists() or AsignacionRol.objects.filter(
        mesa_id__in=ids_sin_electores,
    ).exclude(rol=AsignacionRol.Rol.AUTORIDAD_MESA).exists():
        raise ValueError("Hay mesas sin electores con datos protegidos; revisalas antes de recalcular.")
    afectadas = []
    configuraciones = {c.eleccion_claustro_id: c for c in ConfiguracionAutoridades.objects.filter(eleccion_claustro__eleccion=eleccion)}
    for autoridad in autoridades:
        destino = nuevos_destinos.get(autoridad.registro_padron_id)
        previa = anterior.get(autoridad.registro_padron_id)
        config = configuraciones.get(autoridad.mesa.eleccion_claustro_departamento.eleccion_claustro_id)
        admite_otra_mesa = bool(config and config.permitir_mesa_distinta and destino and destino.sede_id == autoridad.mesa.sede_id)
        compatible = bool(autoridad.mesa_id not in ids_sin_electores and autoridad.mesa_votacion_original_id not in ids_sin_electores
                          and destino and previa and destino.sede_id == autoridad.mesa.sede_id and (
            destino.pk == previa.mesa_id or destino.pk == autoridad.mesa_id or admite_otra_mesa
        ))
        if not compatible:
            afectadas.append(autoridad)
    if afectadas and not confirmar_afectadas:
        raise ValueError("El recálculo afecta designaciones provisorias. Revisá y confirmá la propuesta desde Autoridades.")
    afectadas_ids = {a.pk for a in afectadas}
    if AsignacionAutoridad.objects.filter(mesa_votacion_original_id__in=ids_sin_electores).exclude(pk__in=afectadas_ids).exists():
        raise ValueError("Una mesa sin electores es la mesa anterior de una autoridad que se conserva; revisá su designación.")
    if AsignacionMesa.objects.filter(mesa_id__in=ids_sin_electores).exclude(registro_padron_id__in=nuevos_destinos).exists():
        raise ValueError("Una mesa sin electores activos conserva registros protegidos; revisala antes de recalcular.")
    detalle_afectadas = [{"elector": a.registro_padron.elector.nombre_completo, "mesa": a.mesa.codigo,
                          "turno": str(a.turno)} for a in afectadas]
    for autoridad in afectadas:
        usuarios = PerfilUsuario.objects.filter(elector_id=autoridad.registro_padron.elector_id).values_list("usuario_id", flat=True)
        AsignacionRol.objects.filter(usuario_id__in=usuarios, rol=AsignacionRol.Rol.AUTORIDAD_MESA,
                                     eleccion=eleccion, mesa_id=autoridad.mesa_id).delete()
        CandidaturaAutoridad.objects.filter(pk=autoridad.candidatura_id).update(
            mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None,
            mesa_traslado=None, turno_traslado=None,
        )
        autoridad.delete()
    movimientos = []
    for registro_id, mesa in nuevos_destinos.items():
        fila = anterior.get(registro_id)
        if fila is None:
            AsignacionMesa.objects.create(registro_padron_id=registro_id, mesa=mesa)
            movimientos.append({"registro": registro_id, "origen": None, "destino": mesa.pk})
        elif fila.mesa_id != mesa.pk:
            movimientos.append({"registro": registro_id, "origen": fila.mesa_id, "destino": mesa.pk})
            fila.mesa = mesa
            fila.autoridad_al_final = False
            fila.save(update_fields=("mesa", "autoridad_al_final"))
    if ids_sin_electores:
        CandidaturaAutoridad.objects.filter(mesa_manual_id__in=ids_sin_electores).update(mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None)
        CandidaturaAutoridad.objects.filter(mesa_traslado_id__in=ids_sin_electores).update(mesa_traslado=None, turno_traslado=None)
        AsignacionRol.objects.filter(mesa_id__in=ids_sin_electores, rol=AsignacionRol.Rol.AUTORIDAD_MESA).delete()
        try:
            Mesa.objects.filter(pk__in=ids_sin_electores).delete()
        except ProtectedError as error:
            raise ValueError("Una mesa sin electores tiene datos protegidos; revisala antes de recalcular.") from error
    registrar_evento(accion="padron.mesas_automaticas_recalculadas", entidad="Eleccion", entidad_id=eleccion.pk,
                     eleccion=eleccion, usuario=usuario, request=request,
                     datos_nuevos={"mesas_creadas": creadas, "mesas_quitadas": sorted(ids_sin_electores), "movimientos": movimientos,
                                   "autoridades_vacantes": [a.registro_padron_id for a in afectadas]})
    resumen_autoridades = {}
    for claustro, _alcance, _sede, _es_especial in grupos:
        if CandidaturaAutoridad.objects.filter(registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
                                               excluida=False).exists():
            resumen_autoridades[claustro.pk] = {"pendiente": "Revisá y confirmá la distribución de autoridades desde el claustro."}
    return {"mesas": len(mesas_actuales) + len(creadas) - len(ids_sin_electores), "electores": len(nuevos_destinos),
            "claustros": dict(resumen), "autoridades": resumen_autoridades, "autoridades_vacantes": len(afectadas),
            "detalle_autoridades_vacantes": detalle_afectadas, "movimientos": movimientos,
            "mesas_creadas": creadas, "mesas_quitadas": sorted(ids_sin_electores), "detalle_mesas_quitadas": detalle_quitadas}
