"""Asignación por claustro: titulares de todos los turnos antes de suplentes."""
from collections import Counter, defaultdict, deque
from heapq import heappop, heappush
from random import SystemRandom

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades
from apps.elecciones.models import Eleccion
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import RegistroPadron


def configuracion_actual(claustro):
    return ConfiguracionAutoridades.objects.filter(eleccion_claustro=claustro).first() or ConfiguracionAutoridades(eleccion_claustro=claustro)


def es_candidato_electoral(registro):
    from apps.partidos.models import Candidato
    return Candidato.objects.filter(lista__participacion__eleccion_id=registro.eleccion_id, activo=True).filter(
        Q(elector_id=registro.elector_id) | Q(elector__isnull=True, dni=registro.elector.dni),
    ).exists()


def validar_personas_unicas(registros):
    """No permite que distintos registros de padrón ocupen más de un cupo."""
    electores = [registro.elector_id for registro in registros]
    if len(electores) != len(set(electores)):
        raise ValidationError("No se guardó la distribución: una persona ocupa más de un cupo.")


def bloquear_edicion(claustro):
    eleccion = Eleccion.objects.select_for_update().get(pk=claustro.eleccion_id)
    if eleccion.estado not in (Eleccion.Estado.EN_PREPARACION, Eleccion.Estado.PUBLICADA):
        raise ValidationError("Las autoridades solo pueden distribuirse antes de abrir la elección.")
    if eleccion.autoridades_confirmadas_en:
        raise ValidationError("Las autoridades definitivas ya fueron confirmadas.")
    if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
        raise ValidationError("No se pueden redistribuir autoridades después de emitir el padrón imprimible.")
    if AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion, respondida_en__isnull=False).exists():
        raise ValidationError("Ya hay avisos de ausencia: gestioná los reemplazos sin redistribuir el plantel.")


def _auditar(claustro, usuario, accion, datos):
    from apps.auditoria.services import registrar_evento
    registrar_evento(accion=accion, entidad="EleccionClaustro", entidad_id=claustro.pk,
                    eleccion=claustro.eleccion, usuario=usuario, datos_nuevos=datos)


@transaction.atomic
def eliminar_asignaciones(claustro, usuario):
    """Vacía asignaciones y candidaturas del claustro, sin redistribuir."""
    from django.core.exceptions import PermissionDenied
    from apps.usuarios.models import AsignacionRol
    from apps.usuarios.permisos import puede_gestionar_autoridades

    if not puede_gestionar_autoridades(usuario, claustro.eleccion):
        raise PermissionDenied("No tiene permiso para eliminar asignaciones de autoridades.")
    bloquear_edicion(claustro)
    mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro)
    asignaciones = AsignacionAutoridad.objects.filter(mesa__in=mesas)
    anteriores = list(asignaciones.values(
        "id", "registro_padron_id", "mesa_id", "turno_id", "tipo", "orden_suplencia", "estado",
    ))
    candidaturas = CandidaturaAutoridad.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
    )
    candidaturas_anteriores = list(candidaturas.values(
        "id", "registro_padron_id", "excluida", "mesa_manual_id", "turno_manual_id",
        "tipo_manual", "orden_manual", "mesa_traslado_id", "turno_traslado_id",
    ))
    AsignacionRol.objects.filter(
        rol=AsignacionRol.Rol.AUTORIDAD_MESA, eleccion=claustro.eleccion, mesa__in=mesas,
    ).delete()
    asignaciones.delete()
    candidaturas.delete()
    AsignacionMesa.objects.filter(mesa__in=mesas).update(autoridad_al_final=False)
    _auditar(claustro, usuario, "autoridades.asignaciones_eliminadas", {
        "eliminadas": len(anteriores), "asignaciones_anteriores": anteriores,
        "candidaturas_eliminadas": len(candidaturas_anteriores),
        "candidaturas_anteriores": candidaturas_anteriores,
    })
    return len(anteriores)


def _registros(claustro):
    return RegistroPadron.objects.filter(activo=True, eleccion_claustro_departamento__eleccion_claustro=claustro).select_related(
        "elector", "sede", "turno_cursada", "asignacion_mesa__mesa", "asignacion_sede_padron", "candidatura_autoridad",
    ).order_by("elector__apellido", "elector__nombre", "pk")


def _tipo_mesa_compatible(registro, mesa):
    """El registro debe conservar el tipo de su mesa electoral al ejercer."""
    asignacion = getattr(registro, "asignacion_mesa", None)
    return asignacion is not None and asignacion.mesa.es_especial == mesa.es_especial


def _puede_trabajar(registro, mesa, turno, modo):
    from apps.autoridades.services import _sede_electoral_actual
    propia = getattr(registro, "asignacion_mesa", None)
    candidatura = getattr(registro, "candidatura_autoridad", None)
    traslado = candidatura and candidatura.mesa_traslado_id == mesa.pk and candidatura.turno_traslado_id == turno.pk
    seleccion_fija = candidatura and candidatura.mesa_manual_id == mesa.pk and candidatura.turno_manual_id == turno.pk
    return (
        registro.activo
        and registro.eleccion_claustro_departamento_id == mesa.eleccion_claustro_departamento_id
        and _tipo_mesa_compatible(registro, mesa)
        and (_sede_electoral_actual(registro) == mesa.sede_id or traslado or seleccion_fija)
        and (not registro.sede_id or registro.turno_cursada_id)
        and (not registro.turno_cursada_id or not registro.turno_cursada.se_superpone_con(turno))
        and (modo == ConfiguracionAutoridades.Modo.NOMINA or (propia and propia.mesa_id == mesa.pk) or seleccion_fija)
    )


def _puede_trabajar_nomina(registro, mesa, turno, opciones, tipo="titular", *, traslado_sin_reordenar=False):
    """Aplica los destinos habilitados para nuevas plazas de nómina."""
    from apps.autoridades.services import _sede_electoral_actual
    propia = getattr(registro, "asignacion_mesa", None)
    if not propia or registro.eleccion_claustro_departamento_id != mesa.eleccion_claustro_departamento_id:
        return False
    if not _tipo_mesa_compatible(registro, mesa):
        return False
    if not mesa.sede_id or not mesa.sede.activa:
        return False
    if registro.sede_id and not registro.turno_cursada_id:
        return False
    if registro.turno_cursada_id and registro.turno_cursada.se_superpone_con(turno):
        return False
    candidatura = getattr(registro, "candidatura_autoridad", None)
    if candidatura and candidatura.mesa_traslado_id == mesa.pk and candidatura.turno_traslado_id == turno.pk:
        return True
    if propia.mesa_id == mesa.pk:
        return True
    origen = _sede_electoral_actual(registro)
    if (traslado_sin_reordenar and origen != mesa.sede_id and opciones.permitir_cambio_sede
            and not opciones.reacomodar_titulares and tipo == "titular"):
        from apps.autoridades.reordenamiento_padron import traslado_sin_reordenar
        return traslado_sin_reordenar(registro, mesa)
    if not (opciones.reacomodar_titulares or opciones.permitir_mesa_distinta):
        return False
    if origen == mesa.sede_id:
        return True
    return bool(opciones.reacomodar_titulares and opciones.permitir_cambio_sede and registro.sede_id != origen)


def _completar_plazas(candidatos_por_plaza, fijas):
    """Máxima cobertura por orden de prioridad, conservando los cupos fijos.

    Un camino aumentante reasigna personas sin vaciar plazas ya cubiertas.
    La búsqueda iterativa evita depender del límite de recursión de Python.
    """
    ocupantes = dict(fijas)
    plaza_por_persona = {persona: plaza for plaza, persona in fijas.items()}
    personas_fijas = set(plaza_por_persona)
    if len(personas_fijas) != len(fijas):
        raise ValidationError("Una persona no puede conservar dos cupos de autoridad.")
    for inicio in range(len(candidatos_por_plaza)):
        if inicio in ocupantes:
            continue
        pendientes = deque([inicio])
        predecesoras = {}
        encontrado = False
        while pendientes and not encontrado:
            plaza = pendientes.popleft()
            for persona in candidatos_por_plaza[plaza]:
                if persona in personas_fijas or persona in predecesoras:
                    continue
                predecesoras[persona] = plaza
                anterior = plaza_por_persona.get(persona)
                if anterior is not None:
                    pendientes.append(anterior)
                    continue
                # Recorrer el camino hacia la vacante inicial.
                while persona is not None:
                    destino = predecesoras[persona]
                    desplazada = ocupantes.get(destino)
                    ocupantes[destino] = persona
                    plaza_por_persona[persona] = destino
                    persona = desplazada
                encontrado = True
                break
    return ocupantes


def _optimizar_nomina(candidatos_por_plaza, niveles, fijas):
    """Máxima cobertura y, entre soluciones equivalentes, mínimos traslados.

    Cada opción es ``(registro_id, distancia)``: 0 misma mesa, 1 otra mesa
    de la misma sede, 2 otra sede. Las plazas ya fijadas no se mueven.
    """
    resultado = dict(fijas)
    usadas = set(fijas.values())
    libres = [i for i in range(len(candidatos_por_plaza)) if i not in fijas]
    personas = sorted({persona for i in libres for persona, _ in candidatos_por_plaza[i] if persona not in usadas})
    if not libres or not personas:
        return resultado
    base = len(candidatos_por_plaza) + 1
    origen, inicio_plazas = 0, 1
    inicio_personas = inicio_plazas + len(libres)
    sumidero = inicio_personas + len(personas)
    grafo = [[] for _ in range(sumidero + 1)]

    def arista(a, b, capacidad, costo):
        grafo[a].append([b, len(grafo[b]), capacidad, costo])
        grafo[b].append([a, len(grafo[a]) - 1, 0, -costo])

    nodo_persona = {persona: inicio_personas + i for i, persona in enumerate(personas)}
    recompensa = (base ** 3, base ** 2, base)
    for pos, indice in enumerate(libres):
        nodo = inicio_plazas + pos
        arista(origen, nodo, 1, (recompensa[0] - recompensa[niveles[indice]]) * base * base)
        for persona, distancia in candidatos_por_plaza[indice]:
            if persona in nodo_persona:
                costo = 0 if distancia == 0 else base + int(distancia == 2)
                arista(nodo, nodo_persona[persona], 1, costo)
    for nodo in nodo_persona.values():
        arista(nodo, sumidero, 1, 0)

    potencial = [0] * len(grafo)
    while True:
        distancias = [None] * len(grafo)
        anterior = [None] * len(grafo)
        distancias[origen] = 0
        cola = [(0, origen)]
        while cola:
            distancia, nodo = heappop(cola)
            if distancia != distancias[nodo]:
                continue
            for indice, lado in enumerate(grafo[nodo]):
                destino, _, capacidad, costo = lado
                if not capacidad:
                    continue
                nueva = distancia + costo + potencial[nodo] - potencial[destino]
                if distancias[destino] is None or nueva < distancias[destino]:
                    distancias[destino] = nueva
                    anterior[destino] = (nodo, indice)
                    heappush(cola, (nueva, destino))
        if distancias[sumidero] is None:
            break
        for nodo, distancia in enumerate(distancias):
            if distancia is not None:
                potencial[nodo] += distancia
        nodo = sumidero
        while nodo != origen:
            previo, indice = anterior[nodo]
            lado = grafo[previo][indice]
            lado[2] -= 1
            grafo[nodo][lado[1]][2] += 1
            nodo = previo

    persona_por_nodo = {nodo: persona for persona, nodo in nodo_persona.items()}
    for pos, indice in enumerate(libres):
        for destino, _, capacidad, _ in grafo[inicio_plazas + pos]:
            if destino in persona_por_nodo and capacidad == 0:
                resultado[indice] = persona_por_nodo[destino]
                break
    return resultado


def _resolver_plazas_por_persona(candidatos_por_plaza, fijas, *, modo, niveles):
    """Resuelve por elector y devuelve el registro elegible para cada plaza."""
    registros = {registro.pk: registro for plaza in candidatos_por_plaza for registro, _ in plaza}
    clave_por_elector = {}
    for registro in registros.values():
        clave_por_elector[registro.elector_id] = min(
            clave_por_elector.get(registro.elector_id, registro.pk), registro.pk,
        )
    opciones = []
    for plaza in candidatos_por_plaza:
        por_persona = {}
        for registro, distancia in plaza:
            clave = clave_por_elector[registro.elector_id]
            anterior = por_persona.get(clave)
            if anterior is None or distancia < anterior[1]:
                por_persona[clave] = (registro.pk, distancia)
        opciones.append(por_persona)
    fijas_personas = {plaza: clave_por_elector[registros[registro_id].elector_id] for plaza, registro_id in fijas.items()}
    if len(set(fijas_personas.values())) != len(fijas_personas):
        raise ValidationError("Una persona no puede conservar dos cupos de autoridad.")
    if modo == "nomina":
        candidatos = [[(persona, valor[1]) for persona, valor in plaza.items()] for plaza in opciones]
        solucion = _optimizar_nomina(candidatos, niveles, fijas_personas)
    else:
        solucion = _completar_plazas([list(plaza) for plaza in opciones], fijas_personas)
    return {plaza: fijas[plaza] if plaza in fijas else opciones[plaza][persona][0]
            for plaza, persona in solucion.items()}


def planificar_distribucion(claustro, opciones, mesas, turnos, *, preservar_asignaciones=True, traslado_sin_reordenar=False):
    """Calcula la cobertura sin guardar ni auditar cambios."""
    anteriores = list(AsignacionAutoridad.objects.filter(mesa__in=mesas).order_by("pk"))
    anteriores_por_registro = {a.registro_padron_id: a for a in anteriores if a.estado == "asignada"}
    rechazados = {a.registro_padron_id for a in anteriores if a.estado == "rechazada"}
    previas = {(a.mesa_id, a.turno_id, a.registro_padron_id): a for a in anteriores if a.estado == "asignada"} if preservar_asignaciones else {}
    previas_por_registro = {a.registro_padron_id: a for a in anteriores if a.estado == "asignada"} if preservar_asignaciones else {}
    previas_por_plaza = defaultdict(list)
    if preservar_asignaciones:
        for asignacion in anteriores:
            if asignacion.estado == "asignada":
                clave = (asignacion.mesa_id, asignacion.turno_id, asignacion.tipo, asignacion.orden_suplencia)
                previas_por_plaza[clave].append(asignacion)
    # Una sola consulta para excluir candidatos electorales de todo el padrón.
    from apps.partidos.models import Candidato
    candidatos_electorales = list(Candidato.objects.filter(
        lista__participacion__eleccion_id=claustro.eleccion_id, activo=True,
    ).values_list("elector_id", "dni"))
    electores_candidatos = {elector for elector, _ in candidatos_electorales if elector is not None}
    documentos_candidatos = {dni for elector, dni in candidatos_electorales if elector is None}
    registros = []
    for registro in _registros(claustro):
        candidatura = getattr(registro, "candidatura_autoridad", None)
        if (registro.pk in rechazados or (candidatura and candidatura.excluida)
                or registro.elector_id in electores_candidatos or registro.elector.dni in documentos_candidatos):
            continue
        if opciones.modo != "aleatorio" and not candidatura and registro.pk not in previas_por_registro:
            continue
        registros.append(registro)
    if opciones.modo == "aleatorio":
        sorteo = SystemRandom()
        sorteo.shuffle(registros)
    orden_azar = {r.pk: i for i, r in enumerate(registros)}
    # Primero todos los cupos mínimos, luego los adicionales, en rondas parejas.
    plazas = []
    for es_minimo in (True, False):
        for orden in range(1, max(c.titulares_por_mesa for c in turnos) + 1):
            ronda = []
            for config in turnos:
                if orden <= config.titulares_por_mesa and (orden <= config.minimo_titulares_por_mesa) == es_minimo:
                    for mesa in mesas:
                        ronda.append((mesa, config.turno, "titular", orden))
            if opciones.modo == "aleatorio":
                sorteo.shuffle(ronda)
            plazas.extend(ronda)
    candidatos_por_plaza = []
    for mesa, turno, tipo, orden in plazas:
        elegibles = [r for r in registros if (
            _puede_trabajar_nomina(r, mesa, turno, opciones, tipo, traslado_sin_reordenar=traslado_sin_reordenar)
            if opciones.modo == "nomina" else _puede_trabajar(r, mesa, turno, opciones.modo)
        )]
        # Una propuesta confirmada reserva exactamente su destino laboral.
        elegibles = [r for r in elegibles if not (
            getattr(r, "candidatura_autoridad", None) and r.candidatura_autoridad.mesa_traslado_id
        ) or (r.candidatura_autoridad.mesa_traslado_id == mesa.pk and r.candidatura_autoridad.turno_traslado_id == turno.pk)]
        if opciones.modo == "manual" or any(
            getattr(r, "candidatura_autoridad", None)
            and r.candidatura_autoridad.mesa_manual_id
            for r in elegibles
        ):
            elegibles = [r for r in elegibles if (
                getattr(r, "candidatura_autoridad", None)
                and r.candidatura_autoridad.mesa_manual_id == mesa.pk
                and r.candidatura_autoridad.turno_manual_id == turno.pk
                and r.candidatura_autoridad.tipo_manual == tipo
                and (tipo == "titular" or r.candidatura_autoridad.orden_manual == orden)
            )] if opciones.modo == "manual" else [r for r in elegibles if (
                not getattr(r, "candidatura_autoridad", None)
                or not r.candidatura_autoridad.mesa_manual_id or (
                    r.candidatura_autoridad.mesa_manual_id == mesa.pk
                    and r.candidatura_autoridad.turno_manual_id == turno.pk
                    and r.candidatura_autoridad.tipo_manual == tipo
                    and (tipo == "titular" or r.candidatura_autoridad.orden_manual == orden)
                )
            )]
        # Una asignación vigente puede provenir de otro modo o de una opción
        # que ya se desactivó. Se conserva en su puesto si sigue siendo válida.
        if preservar_asignaciones:
            ids_elegibles = {r.pk for r in elegibles}
            for registro in registros:
                anterior = previas.get((mesa.pk, turno.pk, registro.pk))
                if (anterior and anterior.tipo == tipo
                        and anterior.orden_suplencia == (orden if tipo == "suplente" else None)
                        and registro.pk not in ids_elegibles
                        and registro.eleccion_claustro_departamento_id == mesa.eleccion_claustro_departamento_id
                        and _tipo_mesa_compatible(registro, mesa)
                        and (not registro.sede_id or registro.turno_cursada_id)
                        and (not registro.turno_cursada_id or not registro.turno_cursada.se_superpone_con(turno))):
                    elegibles.append(registro)
        def prioridad(r):
            if opciones.modo == "aleatorio":
                previa = previas.get((mesa.pk, turno.pk, r.pk))
                conserva_lugar = previa and previa.tipo == tipo and (
                    tipo == "titular" or previa.orden_suplencia == orden
                )
                return (0 if conserva_lugar else 1, 0 if r.pk in previas_por_registro else 1, orden_azar[r.pk])
            previa = previas.get((mesa.pk, turno.pk, r.pk))
            propia = getattr(r, "asignacion_mesa", None)
            from apps.autoridades.services import _sede_electoral_actual
            return (
                bool(propia is None or propia.mesa_id != mesa.pk),
                _sede_electoral_actual(r) != mesa.sede_id,
                0 if previa and previa.tipo == tipo else 1 if previa else 2,
                previa.orden_suplencia or 0 if previa else 0,
                orden_azar[r.pk],
            )
        candidatos_por_plaza.append(sorted(elegibles, key=prioridad))
    # Fijar primero las asignaciones vigentes que siguen siendo elegibles y
    # ocupan un cupo válido. Los lugares vacantes se completan con caminos
    # aumentantes, para no bloquear a personas con menos alternativas.
    fijas, personas_fijas = {}, set()
    registro_por_id = {r.pk: r for r in registros}
    for indice, (mesa, turno, tipo, orden) in enumerate(plazas):
        clave = (mesa.pk, turno.pk, tipo, orden if tipo == "suplente" else None)
        # Los titulares no tienen orden: puede haber varias personas bajo
        # la misma clave. Cada una debe ocupar un único cupo.
        elegibles = {r.pk for r in candidatos_por_plaza[indice]}
        previa = next((a for a in previas_por_plaza.get(clave, ())
                       if a.registro_padron_id not in personas_fijas
                       and a.registro_padron_id in elegibles), None)
        if previa:
            fijas[indice] = previa.registro_padron_id
            personas_fijas.add(previa.registro_padron_id)

    if preservar_asignaciones and personas_fijas != set(anteriores_por_registro):
        raise ValidationError("No se pueden conservar todas las asignaciones existentes. Revisá los cupos y las personas asignadas antes de continuar.")

    if opciones.modo == "nomina":
        from apps.autoridades.services import _sede_electoral_actual
        candidatos_con_distancia = []
        for indice, (mesa, _, _, _) in enumerate(plazas):
            candidatos_con_distancia.append([
                (r, 0 if getattr(r, "asignacion_mesa", None) and r.asignacion_mesa.mesa_id == mesa.pk
                 else 1 if _sede_electoral_actual(r) == mesa.sede_id else 2)
                for r in candidatos_por_plaza[indice]
            ])
        minimos = {config.turno_id: config.minimo_titulares_por_mesa for config in turnos}
        niveles = [0 if orden == 1 else 1 if orden <= minimos[turno.pk] else 2
                   for _, turno, _, orden in plazas]
        solucion = _resolver_plazas_por_persona(candidatos_con_distancia, fijas, modo="nomina", niveles=niveles)
    else:
        solucion = _resolver_plazas_por_persona(
            [[(r, 0) for r in candidatos] for candidatos in candidatos_por_plaza], fijas,
            modo=opciones.modo, niveles=[],
        )
    if len(solucion) != len(set(solucion.values())):
        raise ValidationError("No se guardó la distribución: una persona ocupa más de un cupo.")
    ocupantes = {indice: registro_por_id[persona] for indice, persona in solucion.items()}
    return ocupantes, plazas, previas_por_registro, anteriores_por_registro, candidatos_por_plaza


@transaction.atomic
def distribuir(claustro, usuario, *, preservar_asignaciones=True, aplicar_reacomodo=True, traslado_sin_reordenar=False):
    from apps.autoridades.services import _crear_asignacion, _sincronizar_rol_autoridad
    from apps.usuarios.models import AsignacionRol

    bloquear_edicion(claustro)
    opciones = configuracion_actual(claustro)
    mesas = list(Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro).select_related("sede").order_by("numero"))
    turnos = list(claustro.turnos_autoridad.select_related("turno").order_by("turno__hora_inicio", "pk"))
    if not mesas:
        raise ValidationError("Primero deben generarse las mesas del claustro.")
    if not turnos:
        raise ValidationError("Configurá al menos un turno de trabajo.")
    for mesa in mesas:
        mesa.clean()
    if any(c.titulares_por_mesa < 1 for c in turnos):
        raise ValidationError("Cada turno debe tener al menos un titular por mesa.")
    if opciones.modo == "nomina" and not opciones.permitir_cambio_sede:
        CandidaturaAutoridad.objects.filter(
            registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
        ).exclude(registro_padron__asignacion_autoridad__estado="asignada").update(
            mesa_traslado=None, turno_traslado=None,
        )
    if not preservar_asignaciones:
        if opciones.modo != ConfiguracionAutoridades.Modo.ALEATORIO:
            raise ValidationError("Recalcular desde cero requiere el modo de sorteo aleatorio.")
        # Se limpia antes de leer candidaturas, dentro de la misma transacción.
        # Las exclusiones y los datos de votación/cursada siguen siendo reglas
        # de elegibilidad; los destinos laborales anteriores no fijan el sorteo.
        CandidaturaAutoridad.objects.filter(
            registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro,
        ).update(mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None,
                 mesa_traslado=None, turno_traslado=None)
    ocupantes, plazas, previas_por_registro, anteriores_por_registro, candidatos_por_plaza = planificar_distribucion(
        claustro, opciones, mesas, turnos, preservar_asignaciones=preservar_asignaciones,
        traslado_sin_reordenar=traslado_sin_reordenar,
    )
    validar_personas_unicas(ocupantes.values())
    electores_finales = [registro.elector_id for registro in ocupantes.values()]
    if AsignacionAutoridad.objects.filter(
        registro_padron__eleccion_id=claustro.eleccion_id,
        registro_padron__elector_id__in=electores_finales,
    ).exclude(mesa__in=mesas, estado=AsignacionAutoridad.Estado.ASIGNADA).exists():
        raise ValidationError("No se guardó la distribución: una persona ya tiene otra designación en la elección.")
    nuevas = []
    conservadas = []
    registros_finales = set()
    for indice, registro in ocupantes.items():
        mesa, turno, tipo, orden = plazas[indice]
        previa = previas_por_registro.get(registro.pk)
        misma_plaza = previa and (
            previa.mesa_id == mesa.pk
            and previa.turno_id == turno.pk
            and previa.tipo == tipo
            and previa.orden_suplencia == (orden if tipo == "suplente" else None)
        )
        if not getattr(registro, "candidatura_autoridad", None):
            candidatura = CandidaturaAutoridad.objects.create(registro_padron=registro, cargada_por=usuario)
            registro.candidatura_autoridad = candidatura
        if misma_plaza:
            if previa.candidatura_id is None:
                previa.candidatura = registro.candidatura_autoridad
                previa.save(update_fields=("candidatura",))
            conservadas.append(previa)
        else:
            from apps.autoridades.services import _sede_electoral_actual
            if opciones.modo == "nomina" and _sede_electoral_actual(registro) != mesa.sede_id:
                candidatura = registro.candidatura_autoridad
                candidatura.mesa_traslado, candidatura.turno_traslado = mesa, turno
                candidatura.save(update_fields=("mesa_traslado", "turno_traslado"))
            nuevas.append(_crear_asignacion(registro, mesa, turno, usuario, tipo, orden if tipo == "suplente" else None))
        registros_finales.add(registro.pk)
    if not preservar_asignaciones:
        AsignacionRol.objects.filter(rol="autoridad_mesa", eleccion=claustro.eleccion, mesa__in=mesas).delete()
    AsignacionAutoridad.objects.filter(
        mesa__in=mesas, estado=AsignacionAutoridad.Estado.ASIGNADA,
    ).exclude(pk__in=[a.pk for a in conservadas]).delete()
    AsignacionAutoridad.objects.bulk_create(nuevas)
    asignaciones_finales = conservadas + nuevas
    for asignacion in asignaciones_finales:
        _sincronizar_rol_autoridad(asignacion)
    if aplicar_reacomodo and opciones.reacomodar_titulares and opciones.modo == "nomina":
        reacomodar_titulares(claustro, asignaciones_finales, usuario)
    elif aplicar_reacomodo and (opciones.modo != "nomina" or not opciones.permitir_mesa_distinta):
        AsignacionMesa.objects.filter(mesa__in=mesas).update(autoridad_al_final=False)
    # Reportar según las filas efectivamente persistidas, no según el plan local:
    # evita mostrar cobertura completa si alguna escritura no quedó en la base.
    persistidas = list(AsignacionAutoridad.objects.filter(
        mesa__in=mesas, estado=AsignacionAutoridad.Estado.ASIGNADA,
    ).values_list("registro_padron_id", "mesa_id", "turno_id", "tipo", "orden_suplencia"))
    esperadas = [(a.registro_padron_id, a.mesa_id, a.turno_id, a.tipo, a.orden_suplencia)
                 for a in asignaciones_finales]
    if Counter(persistidas) != Counter(esperadas):
        raise ValidationError("No se guardó la distribución: la cobertura no coincide con el cálculo.")
    conteo_persistido = Counter((mesa_id, turno_id, tipo) for _, mesa_id, turno_id, tipo, _ in persistidas)
    faltantes = []
    suplentes_faltantes = 0
    for mesa in mesas:
        for config in turnos:
            titulares_pendientes = max(0, config.titulares_por_mesa - conteo_persistido[(mesa.pk, config.turno_id, "titular")])
            suplentes_pendientes = max(0, config.suplentes_por_mesa - conteo_persistido[(mesa.pk, config.turno_id, "suplente")])
            faltantes.extend([(mesa, config.turno)] * titulares_pendientes)
            suplentes_faltantes += suplentes_pendientes
    ids_previos = set(anteriores_por_registro)
    resumen = {"asignadas": len(persistidas), "conservadas": len(conservadas),
               "nuevas": len(registros_finales - ids_previos),
               "liberadas": len(ids_previos - registros_finales),
               "sin_cubrir": faltantes, "mesas": len(mesas),
               "titulares_faltantes": len(faltantes),
               "suplentes_faltantes": suplentes_faltantes}
    detalle_vacantes = [
        {"mesa": mesa.pk, "turno": turno.pk, "tipo": tipo, "orden": orden,
         "compatibles": len(candidatos_por_plaza[indice]),
         "motivo": "sin_elegibles" if not candidatos_por_plaza[indice] else
                   "sin_combinacion_con_asignaciones_conservadas" if preservar_asignaciones else
                   "compatibles_necesarios_en_otros_cupos"}
        for indice, (mesa, turno, tipo, orden) in enumerate(plazas) if indice not in ocupantes
    ]
    _auditar(claustro, usuario, "autoridades.distribuidas", {
        "modo": opciones.modo, "operacion": "completar" if preservar_asignaciones else "recalcular",
        **{k: v for k, v in resumen.items() if k != "sin_cubrir"},
        "detalle_vacantes": detalle_vacantes,
        "asignaciones_anteriores": [(a.registro_padron_id, a.mesa_id, a.turno_id, a.tipo, a.orden_suplencia)
                                   for a in anteriores_por_registro.values()],
        "asignaciones_resultantes": persistidas,
    })
    return resumen


@transaction.atomic
def promover_suplente_por_baja(mesa, turno, usuario):
    raise ValidationError("Las vacantes de autoridades permanecen sin cubrir; no se designan suplentes.")


def reacomodar_titulares(claustro, autoridades, usuario):
    """Mueve solo lo necesario, conserva capacidad y marca el bloque al pie."""
    titulares = {a.registro_padron_id: a.mesa_id for a in autoridades if a.tipo == "titular" and a.estado == "asignada"}
    suplentes = {a.registro_padron_id for a in autoridades if a.tipo == "suplente"}
    filas = list(AsignacionMesa.objects.filter(registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro).select_related("mesa", "registro_padron__elector").order_by("registro_padron__elector__apellido", "registro_padron__elector__nombre", "pk"))
    destinos = {a.mesa_id: a.mesa for a in autoridades}
    movimientos = [f for f in filas if f.registro_padron_id in titulares and titulares[f.registro_padron_id] != f.mesa_id
                   and destinos[titulares[f.registro_padron_id]].sede_id == f.mesa.sede_id]
    if not movimientos:
        # Mantener el bloque final también cuando ya votan en su mesa de trabajo.
        for fila in filas:
            marcado = titulares.get(fila.registro_padron_id) == fila.mesa_id
            if fila.autoridad_al_final != marcado:
                fila.autoridad_al_final = marcado
                fila.save(update_fields=("autoridad_al_final",))
        return
    if not claustro.maximo_votantes_por_mesa:
        raise ValidationError("Configurá el máximo de electores por mesa antes de reacomodar titulares.")
    if RegistroPadron.objects.filter(eleccion_id=claustro.eleccion_id, qr_generado_en__isnull=False).exists():
        raise ValidationError("No se pueden reacomodar electores con QR emitidos.")
    if any(f.mesa.participaciones.exists() for f in movimientos):
        raise ValidationError("No se pueden reacomodar mesas con participación registrada.")
    originales = {f.pk: f.mesa_id for f in filas}
    mesas = {f.mesa_id: f.mesa for f in filas}
    mesas.update({a.mesa_id: a.mesa for a in autoridades})
    cantidades = Counter(f.mesa_id for f in filas)
    for fila in movimientos:
        cantidades[fila.mesa_id] -= 1
        fila.mesa_id = titulares[fila.registro_padron_id]
        cantidades[fila.mesa_id] += 1
    for mesa_id, mesa in mesas.items():
        while cantidades[mesa_id] > claustro.maximo_votantes_por_mesa:
            desplazable = next((f for f in reversed(filas) if f.mesa_id == mesa_id and f.registro_padron_id not in titulares and f.registro_padron_id not in suplentes), None)
            destinos = [m for m in mesas.values() if m.sede_id == mesa.sede_id and m.eleccion_claustro_departamento_id == mesa.eleccion_claustro_departamento_id and cantidades[m.pk] < claustro.maximo_votantes_por_mesa]
            if not desplazable or not destinos:
                raise ValidationError("No hay capacidad para reacomodar titulares sin superar el máximo por mesa.")
            destino = min(destinos, key=lambda m: (abs(m.numero - mesa.numero), m.numero))
            desplazable.mesa_id = destino.pk
            cantidades[mesa_id] -= 1
            cantidades[destino.pk] += 1
    for fila in filas:
        fila.autoridad_al_final = titulares.get(fila.registro_padron_id) == fila.mesa_id
    AsignacionMesa.objects.bulk_update(filas, ["mesa", "autoridad_al_final"])
    _auditar(claustro, usuario, "autoridades.titulares_reacomodados", {"movimientos": [
        {"registro": f.registro_padron_id, "origen": originales[f.pk], "destino": f.mesa_id}
        for f in filas if originales[f.pk] != f.mesa_id
    ]})


@transaction.atomic
def guardar_selecciones(claustro, selecciones, usuario):
    """Fija selecciones de una mesa o de un archivo sin cambiar el modo global."""
    bloquear_edicion(claustro)
    vistos = set()
    for seleccion in selecciones:
        registro, mesa, turno, tipo, orden = seleccion[:5]
        if tipo != AsignacionAutoridad.Tipo.TITULAR:
            raise ValidationError("Solo se pueden asignar autoridades titulares.")
        asignacion_a_reemplazar = seleccion[5] if len(seleccion) > 5 else None
        if registro.pk in vistos:
            raise ValidationError("Una persona no puede ocupar dos lugares en el archivo.")
        vistos.add(registro.pk)
        if registro.eleccion_claustro_departamento.eleccion_claustro_id != claustro.pk or es_candidato_electoral(registro):
            raise ValidationError("El elector no es elegible como autoridad de este claustro.")
        existente = AsignacionAutoridad.objects.filter(registro_padron=registro, estado="asignada").first()
        if existente and (
            existente.mesa_id != mesa.pk or existente.turno_id != turno.pk
            or existente.tipo != tipo
            or existente.orden_suplencia != (orden if tipo == "suplente" else None)
        ):
            raise ValidationError("La persona ya tiene una asignación; modificala desde el detalle de su mesa.")
        candidatura = getattr(registro, "candidatura_autoridad", None)
        if candidatura and candidatura.excluida:
            raise ValidationError("El elector está excluido de la nómina de autoridades.")
        misma_seleccion = candidatura and (
            candidatura.mesa_manual_id == mesa.pk
            and candidatura.turno_manual_id == turno.pk
            and candidatura.tipo_manual == tipo
        )
        reemplaza_seleccion = candidatura and asignacion_a_reemplazar and (
            candidatura.mesa_manual_id == asignacion_a_reemplazar.mesa_id
            and candidatura.turno_manual_id == asignacion_a_reemplazar.turno_id
            and candidatura.tipo_manual == asignacion_a_reemplazar.tipo
        )
        if candidatura and candidatura.mesa_manual_id and not (
            misma_seleccion or reemplaza_seleccion
            or configuracion_actual(claustro).modo == "manual"
        ):
            raise ValidationError("Esta persona ya tiene una selección manual fija en otra mesa o turno.")
        if not _puede_trabajar(registro, mesa, turno, "manual"):
            raise ValidationError("Seleccioná una persona de esa mesa cuyo turno no se superponga con su horario de asistencia a la sede.")
        config = claustro.turnos_autoridad.filter(turno=turno).first()
        if not config or tipo not in ("titular", "suplente"):
            raise ValidationError("El turno o la función no son válidos.")
        if asignacion_a_reemplazar and (
            asignacion_a_reemplazar.mesa_id != mesa.pk
            or asignacion_a_reemplazar.registro_padron_id == registro.pk
        ):
            raise ValidationError("Elegí una designación distinta de la persona que vas a asignar, dentro de esta mesa.")
        if asignacion_a_reemplazar and asignacion_a_reemplazar.candidatura_id:
            CandidaturaAutoridad.objects.filter(pk=asignacion_a_reemplazar.candidatura_id).update(
                mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None,
            )
        if tipo == "suplente" and (not orden or orden < 1 or orden > config.suplentes_por_mesa):
            raise ValidationError("El orden de suplencia supera el cupo del turno.")
        CandidaturaAutoridad.objects.update_or_create(registro_padron=registro, defaults={
            "cargada_por": usuario, "mesa_manual": mesa, "turno_manual": turno,
            "tipo_manual": tipo, "orden_manual": orden if tipo == "suplente" else None,
        })
    ocupacion = Counter()
    ordenes = set()
    for c in CandidaturaAutoridad.objects.filter(registro_padron__eleccion_claustro_departamento__eleccion_claustro=claustro, excluida=False, mesa_manual__isnull=False):
        clave = (c.mesa_manual_id, c.turno_manual_id, c.tipo_manual)
        ocupacion[clave] += 1
        if c.tipo_manual == "suplente":
            clave_orden = (*clave, c.orden_manual)
            if clave_orden in ordenes:
                raise ValidationError("Hay dos suplentes con el mismo orden en una mesa y turno.")
            ordenes.add(clave_orden)
        config = claustro.turnos_autoridad.get(turno_id=c.turno_manual_id)
        limite = config.titulares_por_mesa if c.tipo_manual == "titular" else config.suplentes_por_mesa
        if ocupacion[clave] > limite:
            raise ValidationError("La selección supera el cupo de autoridades de la mesa y turno.")
    if configuracion_actual(claustro).modo == "manual" and any(clave[2] == "suplente" for clave in ocupacion):
        mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro)
        for mesa in mesas:
            for config in claustro.turnos_autoridad.all():
                if ocupacion[(mesa.pk, config.turno_id, "titular")] < config.titulares_por_mesa:
                    raise ValidationError("Primero completá los titulares de todas las mesas y turnos; después seleccioná suplentes.")
    resumen = distribuir(claustro, usuario)
    _auditar(claustro, usuario, "autoridades.seleccion_manual", {"registros": sorted(vistos)})
    return resumen
