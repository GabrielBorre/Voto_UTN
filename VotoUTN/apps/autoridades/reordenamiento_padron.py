"""Cálculo en memoria del padrón con titulares al final de su mesa."""
from collections import defaultdict
from dataclasses import dataclass
from math import ceil

from django.core.exceptions import ValidationError
from django.db.models import Q


@dataclass(frozen=True)
class GrupoPadron:
    claustro: object
    departamento: object
    sede: object
    es_especial: bool = False


@dataclass(frozen=True)
class MesaPropuesta:
    identificador: object
    grupo: object


@dataclass(frozen=True)
class ElectorPropuesto:
    identificador: object
    grupo: object


def _ubicacion_sin_reordenar(registro, destino, *, verificar_cursada=True):
    from apps.mesas.models import AsignacionMesa
    from apps.padron.models import SolicitudCambioSede
    fila = AsignacionMesa.objects.select_related("mesa").filter(registro_padron=registro).first()
    if not fila or not destino.sede_id or not destino.sede.activa:
        return False
    if fila.mesa.sede_id == destino.sede_id or fila.mesa.eleccion_claustro_departamento_id != destino.eleccion_claustro_departamento_id:
        return False
    if fila.mesa.es_especial != destino.es_especial:
        return False
    if (verificar_cursada and registro.sede_id == fila.mesa.sede_id) or registro.qr_generado_en:
        return False
    if SolicitudCambioSede.objects.filter(registro_padron=registro, estado="pendiente").exists():
        return False
    try:
        destino.clean()
    except ValidationError:
        return False
    maximo = destino.eleccion_claustro_departamento.eleccion_claustro.maximo_votantes_por_mesa
    filas = list(AsignacionMesa.objects.filter(
        Q(mesa__eleccion_claustro_departamento=destino.eleccion_claustro_departamento,
          mesa__sede=destino.sede, mesa__es_especial=destino.es_especial) | Q(registro_padron=registro),
    ).select_related("mesa").order_by(
        "registro_padron__elector__apellido", "registro_padron__elector__nombre", "registro_padron_id",
    ))
    if not maximo or sum(f.mesa_id == destino.pk for f in filas) >= maximo:
        return False
    antes_del_traslado = True
    for otra in filas:
        if otra.registro_padron_id == registro.pk:
            antes_del_traslado = False
            continue
        if (antes_del_traslado and otra.mesa.numero > destino.numero) or (not antes_del_traslado and otra.mesa.numero < destino.numero):
            return False
    return True


def _planificar_traslado_sin_reordenar(registro, destino, *, verificar_cursada=True):
    """Busca destinos para todos los registros sin desplazar a otras personas."""
    from apps.elecciones.models import EleccionClaustroDepartamentoSede
    from apps.mesas.models import AsignacionMesa, Mesa
    from apps.padron.models import RegistroPadron, SolicitudCambioSede

    if not _ubicacion_sin_reordenar(registro, destino, verificar_cursada=verificar_cursada):
        return None
    registros = list(RegistroPadron.objects.filter(
        eleccion_id=registro.eleccion_id, elector_id=registro.elector_id, activo=True,
    ).select_related("eleccion_claustro_departamento").order_by("-es_principal", "pk"))
    if len(registros) == 1 and registros[0].es_principal:
        if SolicitudCambioSede.objects.filter(registro_padron=registro, estado="aprobada").exclude(
            sede_destino_id=destino.sede_id,
        ).exists():
            return None
        return [(registro, destino)]
    principales = [item for item in registros if item.es_principal]
    if len(principales) != 1:
        return None
    principal = principales[0]
    if not EleccionClaustroDepartamentoSede.objects.filter(
        eleccion_claustro_departamento=principal.eleccion_claustro_departamento,
        sede_id=destino.sede_id, sede__activa=True,
    ).exists():
        return None
    solicitudes = SolicitudCambioSede.objects.filter(
        registro_padron__eleccion_id=registro.eleccion_id, registro_padron__elector_id=registro.elector_id,
    )
    if solicitudes.filter(estado="pendiente").exists() or solicitudes.filter(estado="aprobada").exclude(sede_destino_id=destino.sede_id).exists():
        return None
    origen = AsignacionMesa.objects.filter(registro_padron=registro).values_list("mesa__sede_id", flat=True).first()
    resultado = []
    for item in registros:
        sede_actual = AsignacionMesa.objects.filter(registro_padron=item).values_list("mesa__sede_id", flat=True).first()
        if sede_actual != origen or item.qr_generado_en:
            return None
        if item.pk == registro.pk:
            mesa = destino
        else:
            candidatas = Mesa.objects.filter(
                eleccion_id=registro.eleccion_id, eleccion_claustro_departamento_id=item.eleccion_claustro_departamento_id,
                sede_id=destino.sede_id, es_especial=not item.es_principal,
            ).select_related("sede", "eleccion_claustro_departamento__eleccion_claustro").order_by("numero", "pk")
            mesa = next((opcion for opcion in candidatas if _ubicacion_sin_reordenar(item, opcion, verificar_cursada=False)), None)
            if mesa is None:
                return None
        resultado.append((item, mesa))
    return resultado


def traslado_sin_reordenar(registro, destino):
    """Comprueba el traslado conjunto sin desplazar a otros electores."""
    return _planificar_traslado_sin_reordenar(registro, destino) is not None


def aplicar_traslados_sin_reordenar(asignaciones):
    from apps.mesas.models import AsignacionMesa
    from apps.padron.models import AsignacionSedePadron
    movimientos = []
    for asignacion in asignaciones:
        registro, destino = asignacion.registro_padron, asignacion.mesa
        fila = AsignacionMesa.objects.select_for_update().select_related("mesa").get(registro_padron=registro)
        if fila.mesa.sede_id == destino.sede_id:
            continue
        propuesta = _planificar_traslado_sin_reordenar(registro, destino)
        if propuesta is None:
            raise ValidationError("El traslado ya no respeta el orden o la capacidad sin mover otras mesas.")
        for item, mesa in propuesta:
            fila_item = AsignacionMesa.objects.select_for_update().select_related("mesa").get(registro_padron=item)
            origen_id = fila_item.mesa_id
            sede = AsignacionSedePadron.objects.select_for_update().get(registro_padron=item)
            sede.sede_id = mesa.sede_id
            sede.regla_aplicada = None
            sede.estado = AsignacionSedePadron.Estado.ASIGNADA
            sede.full_clean()
            sede.save()
            fila_item.mesa = mesa
            if item.pk == registro.pk:
                fila_item.autoridad_al_final = True
            fila_item.full_clean()
            fila_item.save(update_fields=("mesa", "autoridad_al_final"))
            movimientos.append({"registro": item.pk, "origen": origen_id, "destino": mesa.pk})
    return movimientos


def calcular_padrones_ordenados(*, mesas, electores, titulares, maximo,
                               votacion_fija=None, mesas_protegidas=(), destinos_adicionales=None):
    """Planifica sin escribir; el orden de entrada de electores es alfabético.

    ``grupo`` representa un mismo claustro, departamento y sede. ``titulares``
    vincula cada elector titular con la mesa de trabajo que deberá reservarlo.
    Las mesas existentes se conservan en su orden de entrada y las nuevas usan
    identificadores provisionales (grupo, índice). El llamador debe comprobar
    permisos, referencias y que sea seguro retirar o crear cada mesa.
    """
    if not isinstance(maximo, int) or isinstance(maximo, bool) or maximo < 1:
        raise ValidationError("Configurá un máximo de electores por mesa válido.")
    mesas = list(mesas)
    electores = list(electores)
    votacion_fija = votacion_fija or {}
    destinos_adicionales = destinos_adicionales or {}
    mesas_protegidas = set(mesas_protegidas)
    mesas_por_id = {m.identificador: m for m in mesas}
    electores_por_id = {e.identificador: e for e in electores}
    if len(mesas_por_id) != len(mesas) or len(electores_por_id) != len(electores):
        raise ValidationError("Hay mesas o electores repetidos en el cálculo.")
    if any(e.identificador is None for e in electores) or any(
        not isinstance(elemento.grupo, GrupoPadron) for elemento in [*mesas, *electores]
    ):
        raise ValidationError("Faltan identificadores o el alcance del padrón es inválido.")
    if any(e not in electores_por_id or m not in mesas_por_id for e, m in titulares.items()):
        raise ValidationError("Una autoridad o mesa del cálculo ya no está disponible.")
    if any(e not in electores_por_id or m not in mesas_por_id for e, m in votacion_fija.items()) or not mesas_protegidas.issubset(mesas_por_id):
        raise ValidationError("Una asignación o mesa protegida ya no está disponible.")
    for elector_id, destino in destinos_adicionales.items():
        if elector_id not in electores_por_id or not isinstance(destino, GrupoPadron):
            raise ValidationError("Un registro adicional o su destino ya no está disponible.")
        origen = electores_por_id[elector_id].grupo
        if (origen.claustro, origen.departamento, origen.es_especial) != (destino.claustro, destino.departamento, destino.es_especial):
            raise ValidationError("Un registro adicional no puede cambiar de claustro, departamento ni tipo de mesa.")
        mesa_fija = titulares.get(elector_id, votacion_fija.get(elector_id))
        if mesa_fija is not None and mesas_por_id[mesa_fija].grupo != destino:
            raise ValidationError("Una asignación protegida impide el traslado conjunto.")
    if set(titulares) & set(votacion_fija):
        raise ValidationError("Una persona no puede tener dos reservas en el padrón.")
    for elector_id, mesa_id in titulares.items():
        origen = electores_por_id[elector_id].grupo
        destino = mesas_por_id[mesa_id].grupo
        if (origen.claustro, origen.departamento) != (destino.claustro, destino.departamento):
            raise ValidationError("Una autoridad no puede cambiar de claustro ni de departamento.")
        if origen.es_especial != destino.es_especial:
            raise ValidationError("Una autoridad no puede cambiar el tipo de su mesa electoral.")
    if any(electores_por_id[e].grupo != mesas_por_id[m].grupo for e, m in votacion_fija.items()):
        raise ValidationError("No se puede cambiar de sede a una persona con votación fijada.")

    mesas_grupo = defaultdict(list)
    for mesa in mesas:
        mesas_grupo[mesa.grupo].append(mesa.identificador)
    registros_grupo = defaultdict(list)
    reservas = defaultdict(list)
    fijos = defaultdict(list)
    orden = {e.identificador: i for i, e in enumerate(electores)}
    for elector in electores:
        destino = titulares.get(elector.identificador, votacion_fija.get(elector.identificador))
        grupo = mesas_por_id[destino].grupo if destino is not None else destinos_adicionales.get(elector.identificador, elector.grupo)
        registros_grupo[grupo].append(elector.identificador)
        if elector.identificador in titulares:
            reservas[destino].append(elector.identificador)
        elif elector.identificador in votacion_fija:
            fijos[destino].append(elector.identificador)
    if any(len(reservas[mesa]) + len(fijos[mesa]) > maximo for mesa in mesas_por_id):
        raise ValidationError("Los titulares de una mesa superan su capacidad de electores.")

    grupos = set(mesas_grupo) | set(registros_grupo)
    padrones, nuevas, quitadas = {}, [], []
    for grupo in sorted(grupos, key=str):
        existentes = mesas_grupo[grupo]
        registros = registros_grupo[grupo]
        ultima_reserva = max((i + 1 for i, mesa in enumerate(existentes)
                              if reservas[mesa] or fijos[mesa] or mesa in mesas_protegidas), default=0)
        cantidad = max(ceil(len(registros) / maximo), ultima_reserva)
        elegidas = list(existentes[:cantidad])
        quitadas.extend(existentes[cantidad:])
        for indice in range(len(existentes), cantidad):
            provisional = (grupo, indice + 1)
            if provisional in mesas_por_id:
                raise ValidationError("No se pudo identificar una mesa provisional de forma única.")
            nuevas.append(MesaPropuesta(provisional, grupo))
            elegidas.append(provisional)

        pendientes = iter(e for e in registros if e not in titulares and e not in votacion_fija)
        for mesa in elegidas:
            bloque = reservas[mesa]
            personas = list(fijos[mesa])
            for _ in range(maximo - len(bloque) - len(personas)):
                persona = next(pendientes, None)
                if persona is None:
                    break
                personas.append(persona)
            padrones[mesa] = sorted(personas, key=orden.__getitem__) + bloque
        if next(pendientes, None) is not None:
            raise ValidationError("No hay capacidad suficiente para el padrón calculado.")
    return {"padrones": padrones, "mesas_nuevas": nuevas, "mesas_quitadas": quitadas}


def previsualizar_padrones(claustro, *, titulares, permitir_cambio_mesa, permitir_cambio_sede,
                           registros_conservados=(), votacion_fija_adicional=None):
    """Lee el padrón y calcula su distribución sin cambiar filas ni emitir QR.

    ``titulares`` contiene identificadores de registros y de mesas de trabajo
    ya calculadas. El resultado es una propuesta; no autoriza eliminar mesas ni
    reemplaza la revalidación y el bloqueo transaccional al confirmarla.
    """
    from apps.autoridades.models import AsignacionAutoridad
    from apps.elecciones.models import EleccionClaustroDepartamentoSede
    from apps.mesas.models import AsignacionMesa, Mesa
    from apps.padron.models import RegistroPadron, SolicitudCambioSede

    mesas = list(Mesa.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro=claustro,
    ).select_related("eleccion_claustro_departamento__departamento", "sede").order_by("numero", "pk"))
    filas = list(AsignacionMesa.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
    ).select_related("mesa", "registro_padron__elector").order_by(
        "registro_padron__elector__apellido", "registro_padron__elector__nombre", "registro_padron_id",
    ))
    mesas_por_id = {mesa.pk: mesa for mesa in mesas}
    filas_por_registro = {fila.registro_padron_id: fila for fila in filas}
    registros_conservados = set(registros_conservados)
    if any(fila.mesa_id not in mesas_por_id for fila in filas):
        raise ValidationError("Hay electores asignados a mesas fuera de este claustro.")
    asignaciones = list(AsignacionAutoridad.objects.filter(
        mesa__in=mesas, estado=AsignacionAutoridad.Estado.ASIGNADA,
    ).values_list("registro_padron_id", "mesa_id", "tipo"))
    for registro_id, mesa_id, tipo in asignaciones:
        if tipo == "titular" and titulares.get(registro_id) != mesa_id:
            raise ValidationError("La previsualización debe conservar las autoridades titulares ya asignadas.")
    for registro_id, mesa_id in titulares.items():
        fila, destino = filas_por_registro.get(registro_id), mesas_por_id.get(mesa_id)
        if not fila or not destino:
            raise ValidationError("Una autoridad o mesa del cálculo ya no está disponible.")
        origen = fila.mesa
        if origen.eleccion_claustro_departamento_id != destino.eleccion_claustro_departamento_id:
            raise ValidationError("Una autoridad no puede cambiar de claustro ni de departamento.")
        if registro_id in registros_conservados:
            continue
        if origen.sede_id != destino.sede_id:
            if not permitir_cambio_sede:
                raise ValidationError("El cambio de sede no está habilitado.")
            if not permitir_cambio_mesa:
                raise ValidationError("El cambio de sede requiere habilitar el cambio de mesa.")
            if fila.registro_padron.sede_id == origen.sede_id:
                raise ValidationError("No se puede trasladar a quien cursa en su sede electoral de origen.")
            if not destino.sede_id or not destino.sede.activa:
                raise ValidationError("La sede de destino debe estar activa y habilitada.")
            destino.clean()
        elif origen.pk != destino.pk and not permitir_cambio_mesa:
            raise ValidationError("El cambio de mesa no está habilitado.")

    def grupo(mesa):
        return GrupoPadron(claustro.pk, mesa.eleccion_claustro_departamento_id, mesa.sede_id, mesa.es_especial)

    destinos_adicionales = {}
    cambios_sede = []
    for registro_id, mesa_id in titulares.items():
        fila, destino = filas_por_registro[registro_id], mesas_por_id[mesa_id]
        if registro_id not in registros_conservados and fila.mesa.sede_id != destino.sede_id:
            cambios_sede.append((fila, destino))
    electores_cambio = {fila.registro_padron.elector_id for fila, _ in cambios_sede}
    registros_personas = defaultdict(list)
    for registro in RegistroPadron.objects.filter(
        eleccion=claustro.eleccion, activo=True, elector_id__in=electores_cambio,
    ).select_related("eleccion_claustro_departamento"):
        registros_personas[registro.elector_id].append(registro)
    for fila, destino in cambios_sede:
        persona_id = fila.registro_padron.elector_id
        registros = registros_personas[persona_id]
        principales = [registro for registro in registros if registro.es_principal]
        if len(principales) != 1 or any(registro.pk not in filas_por_registro for registro in registros):
            raise ValidationError("La persona no tiene todos sus registros activos con una mesa asignada.")
        principal = principales[0]
        if not EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento_id=principal.eleccion_claustro_departamento_id,
            sede_id=destino.sede_id, sede__activa=True,
        ).exists():
            raise ValidationError("La sede de destino no está habilitada para el departamento principal.")
        solicitudes = SolicitudCambioSede.objects.filter(
            registro_padron__eleccion=claustro.eleccion, registro_padron__elector_id=persona_id,
        )
        if solicitudes.filter(estado="pendiente").exists():
            raise ValidationError("Una autoridad tiene una solicitud de cambio de sede pendiente. Resolvela antes de modificar su sede electoral.")
        if solicitudes.filter(estado="aprobada").exclude(sede_destino_id=destino.sede_id).exists():
            raise ValidationError("Una solicitud de cambio de sede aprobada impide el traslado conjunto.")
        for registro in registros:
            otra_fila = filas_por_registro[registro.pk]
            if otra_fila.mesa.sede_id != fila.mesa.sede_id or registro.qr_generado_en:
                raise ValidationError("Los registros de la persona no comparten una sede modificable.")
            if registro.pk != fila.registro_padron_id:
                destinos_adicionales[registro.pk] = GrupoPadron(
                    claustro.pk, otra_fila.mesa.eleccion_claustro_departamento_id,
                    destino.sede_id, otra_fila.mesa.es_especial,
                )

    votacion_fija = {registro_id: filas_por_registro[registro_id].mesa_id
                     for registro_id, _, tipo in asignaciones
                     if tipo == "suplente" and registro_id not in titulares and registro_id in filas_por_registro}
    votacion_fija.update(votacion_fija_adicional or {})
    propuesta = calcular_padrones_ordenados(
        mesas=[MesaPropuesta(m.pk, grupo(m)) for m in mesas],
        electores=[ElectorPropuesto(f.registro_padron_id, grupo(f.mesa)) for f in filas],
        titulares=titulares,
        maximo=claustro.maximo_votantes_por_mesa,
        votacion_fija=votacion_fija,
        destinos_adicionales=destinos_adicionales,
        mesas_protegidas={m.pk for m in mesas if not m.generada_automaticamente
                          or m.estado_escaneo != Mesa.EstadoEscaneo.PENDIENTE}
                         | {mesa_id for _, mesa_id, _ in asignaciones} | set(votacion_fija.values())
                         | set(AsignacionAutoridad.objects.filter(mesa__in=mesas, mesa_votacion_original__isnull=False)
                               .values_list("mesa_votacion_original_id", flat=True))
                         | set(Mesa.objects.filter(pk__in=mesas_por_id).filter(
                             Q(asignaciones_rol__isnull=False)
                             | Q(selecciones_autoridad__isnull=False)
                             | Q(traslados_autoridad__isnull=False)
                             | Q(participaciones__isnull=False)
                         ).values_list("pk", flat=True)),
    )
    resumen = defaultdict(lambda: {"actuales": 0, "nuevas": 0, "quitadas": 0})
    for mesa in mesas:
        resumen[grupo(mesa)]["actuales"] += 1
    for mesa in propuesta["mesas_nuevas"]:
        resumen[mesa.grupo]["nuevas"] += 1
    for mesa_id in propuesta["mesas_quitadas"]:
        resumen[grupo(mesas_por_id[mesa_id])]["quitadas"] += 1
    propuesta["resumen_mesas"] = dict(resumen)
    return propuesta


def aplicar_padrones(claustro, propuesta, *, titulares):
    """Aplica una propuesta ya validada dentro de la transacción del llamador."""
    from django.db import transaction
    from django.db.models import Max
    from django.db.models.deletion import ProtectedError
    from apps.elecciones.models import Eleccion
    from apps.mesas.models import AsignacionMesa, Mesa
    from apps.padron.models import AsignacionSedePadron, RegistroPadron, SolicitudCambioSede

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Aplicar el padrón requiere una transacción activa.")
    Eleccion.objects.select_for_update().get(pk=claustro.eleccion_id)
    filas = {fila.registro_padron_id: fila for fila in AsignacionMesa.objects.select_for_update().filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
    ).select_related("mesa", "registro_padron")}
    destinos = list(propuesta["padrones"].values())
    ids = [registro for grupo in destinos for registro in grupo]
    if len(ids) != len(set(ids)) or set(ids) != set(filas):
        raise ValidationError("El padrón cambió; calculá una nueva previsualización.")
    mesas = {m.pk: m for m in Mesa.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro=claustro,
    ).select_related("eleccion_claustro_departamento__eleccion_claustro")}
    siguiente = (Mesa.objects.filter(eleccion=claustro.eleccion).aggregate(valor=Max("numero"))["valor"] or 0) + 1
    for nueva in propuesta["mesas_nuevas"]:
        mesa = Mesa(
            eleccion=claustro.eleccion, numero=siguiente,
            eleccion_claustro_departamento_id=nueva.grupo.departamento,
            sede_id=nueva.grupo.sede, generada_automaticamente=True, es_especial=nueva.grupo.es_especial,
        )
        mesa.full_clean()
        mesa.save()
        mesas[nueva.identificador] = mesa
        siguiente += 1
    asignaciones_propuestas = []
    for mesa_id, registros in propuesta["padrones"].items():
        mesa = mesas.get(mesa_id)
        if mesa is None:
            raise ValidationError("Una mesa de la propuesta ya no existe; calculá nuevamente.")
        for registro_id in registros:
            asignaciones_propuestas.append((filas[registro_id], mesa))
    por_persona = defaultdict(list)
    for fila, mesa in asignaciones_propuestas:
        if fila.registro_padron.activo:
            por_persona[fila.registro_padron.elector_id].append((fila, mesa))
    registros_activos = RegistroPadron.objects.filter(
        eleccion=claustro.eleccion, activo=True, elector_id__in=por_persona,
    )
    if set(registros_activos.values_list("pk", flat=True)) != {
        fila.registro_padron_id for asignaciones in por_persona.values() for fila, _ in asignaciones
    }:
        raise ValidationError("Faltan registros activos en la propuesta; calculá nuevamente el padrón.")
    personas_multiples = {elector_id for elector_id, asignaciones in por_persona.items() if len(asignaciones) > 1}
    for elector_id in personas_multiples:
        grupo_persona = por_persona[elector_id]
        if len({mesa.sede_id for _, mesa in grupo_persona}) != 1 or sum(fila.registro_padron.es_principal for fila, _ in grupo_persona) != 1:
            raise ValidationError("Los registros de una persona deben conservar una única sede electoral y un principal.")

    movimientos = []
    for fila, mesa in sorted(asignaciones_propuestas, key=lambda item: not item[0].registro_padron.es_principal):
        registro_id = fila.registro_padron_id
        original = fila.mesa
        if original.pk != mesa.pk:
            movimientos.append({"registro": registro_id, "origen": original.pk, "destino": mesa.pk})
            if original.sede_id != mesa.sede_id:
                solicitudes = SolicitudCambioSede.objects.filter(
                    registro_padron__elector_id=fila.registro_padron.elector_id,
                    registro_padron__eleccion=claustro.eleccion,
                )
                if solicitudes.filter(estado="pendiente").exists() or solicitudes.filter(estado="aprobada").exclude(sede_destino_id=mesa.sede_id).exists():
                    raise ValidationError("Una solicitud de cambio de sede impide modificar la sede electoral.")
                asignacion = AsignacionSedePadron.objects.filter(registro_padron_id=registro_id).first()
                if asignacion is None:
                    raise ValidationError("Falta la sede electoral de un elector; calculá nuevamente el padrón.")
                asignacion.sede_id = mesa.sede_id
                asignacion.regla_aplicada = None
                asignacion.estado = AsignacionSedePadron.Estado.ASIGNADA
                asignacion.full_clean()
                asignacion.save()
            fila.mesa = mesa
        fila.autoridad_al_final = registro_id in titulares
        fila.full_clean()
    AsignacionMesa.objects.bulk_update(filas.values(), ("mesa", "autoridad_al_final"))
    try:
        Mesa.objects.filter(pk__in=propuesta["mesas_quitadas"], generada_automaticamente=True).delete()
    except ProtectedError as error:
        raise ValidationError("Una mesa que se intentó quitar tiene datos vinculados; calculá nuevamente.") from error
    return movimientos
