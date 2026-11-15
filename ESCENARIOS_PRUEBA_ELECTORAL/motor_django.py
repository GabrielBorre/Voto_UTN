"""Adaptador de pruebas: usa modelos, formularios y servicios del proyecto existente."""
from collections import Counter

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.autoridades.distribucion import bloquear_edicion
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.elecciones.models import Eleccion
from apps.justificativos.forms import FormularioJustificativo
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.forms import FormularioSolicitudCambioSede
from apps.padron.solicitudes_escenario import crear_solicitudes_escenario
from apps.padron.models import RegistroPadron, SolicitudCambioSede
from apps.padron.services import estimar_impacto_mesas_por_sede, solicitudes_cambio_sede_habilitadas
from apps.usuarios.permisos import puede_gestionar_autoridades


def exigir(condicion, mensaje):
    if not condicion:
        raise ValidationError(mensaje)


def validar_eleccion(eleccion, control, *, solo_estudiantes=False):
    c = control['configuracion']
    exigir(eleccion.estado in ('en_preparacion', 'publicada'), 'La elección debe estar en preparación o publicada.')
    configuraciones = {ec.claustro.abreviatura: ec for ec in eleccion.elecciones_claustro.select_related('claustro')}
    if solo_estudiantes:
        exigir(c['codigos_claustro']['estudiantes'] in configuraciones, 'La elección no tiene el claustro estudiantil esperado.')
    else:
        exigir(set(configuraciones) == set(c['codigos_claustro'].values()), 'Los cuatro códigos de claustro deben coincidir con DECISIONES.md.')
    registros = {}
    for cl, esperado in control['claustros'].items():
        if solo_estudiantes and cl != 'estudiantes':
            continue
        ec = configuraciones[c['codigos_claustro'][cl]]
        exigir(ec.maximo_votantes_por_mesa == c['maximo_mesa'][cl], f'{cl}: máximo por mesa diferente.')
        turnos = {t.turno.nombre: (t.minimo_titulares_por_mesa, t.titulares_por_mesa)
                  for t in ec.turnos_autoridad.select_related('turno')}
        exigir(turnos == {t: (c['autoridades']['minimo'], c['autoridades']['maximo']) for t in c['turnos']}, f'{cl}: turnos o cupos diferentes.')
        alcances = {a.pk: a for a in ec.departamentos.select_related('departamento').prefetch_related('sedes_habilitadas__sede')}
        sedes_alcance = {pk: {s.sede.nombre for s in a.sedes_habilitadas.all()} for pk, a in alcances.items()}
        rs = list(RegistroPadron.objects.filter(activo=True, eleccion=eleccion,
                  eleccion_claustro_departamento__eleccion_claustro=ec).select_related(
                  'elector', 'eleccion_claustro_departamento__departamento', 'asignacion_sede_padron__sede',
                  'asignacion_mesa__mesa', 'turno_cursada'))
        exigir(len(rs) == esperado['filas'] and len({r.elector_id for r in rs}) == esperado['personas'], f'{cl}: cantidad de registros o personas diferente.')
        esperado_por_persona = Counter(dni for m in esperado['mesas'] for dni in m['personas'])
        exigir(Counter(r.elector.dni for r in rs) == esperado_por_persona, f'{cl}: las identidades no corresponden al escenario.')
        for r in rs:
            alcance = r.eleccion_claustro_departamento
            depto = alcance.departamento.codigo if alcance.departamento_id else ''
            sedes = sedes_alcance[alcance.pk]
            if cl == 'estudiantes':
                unica = c['sede_unica_estudiantes'].get(depto)
                habilitadas = {unica} if unica else set(c['sedes'])
            elif cl in c['sede_electoral']:
                habilitadas = {c['sede_electoral'][cl]}
            else:
                habilitadas = set(c['sedes'])
            exigir(sedes == habilitadas, f'{cl}/{depto}: sedes habilitadas diferentes.')
            exigir(hasattr(r, 'asignacion_mesa') and hasattr(r, 'asignacion_sede_padron'), 'Calculá sedes y mesas antes de ejecutar los scripts.')
            exigir(r.asignacion_mesa.mesa.sede_id == r.asignacion_sede_padron.sede_id, 'Mesa y sede electoral no coinciden.')
        registros[cl] = rs
    return registros


@transaction.atomic
def ejecutar(datos):
    eleccion = Eleccion.objects.select_for_update().get(pk=datos['eleccion'])
    control = datos['control']
    rs = validar_eleccion(eleccion, control, solo_estudiantes=datos.get('solo_estudiantes', False))
    accion = datos['accion']
    resultado = {'eleccion': eleccion.pk, 'segmento': control['segmento']['carpeta'], 'accion': accion,
                 'aplicado': bool(datos['aplicar'])}
    estudiantes = rs['estudiantes']
    solicitantes = {f['dni'] for f in control['solicitudes']}
    excluidos = solicitantes | {'38999222'}
    registros_reservados = [r for r in estudiantes if r.elector.dni in excluidos]
    exigir(len(registros_reservados) == len(excluidos), 'Las reservas deben tener un único registro por persona.')
    if accion == 'reservar':
        exigir(bool(datos.get('usuario')), 'Indicá --usuario con un usuario local autorizado.')
        usuario = get_user_model().objects.get(username=datos['usuario'], is_active=True)
        exigir(puede_gestionar_autoridades(usuario, eleccion), 'El usuario no puede gestionar autoridades de esta elección.')
        bloquear_edicion(registros_reservados[0].eleccion_claustro_departamento.eleccion_claustro)
        exigir(not AsignacionAutoridad.objects.filter(registro_padron__in=registros_reservados).exists(), 'Hay solicitantes ya designados: reservá antes del sorteo.')
        for r in registros_reservados:
            candidatura, _ = CandidaturaAutoridad.objects.get_or_create(registro_padron=r, defaults={'cargada_por': usuario})
            exigir(not candidatura.mesa_manual_id and not candidatura.mesa_traslado_id, 'Una reserva ya tiene una selección manual o traslado.')
            candidatura.excluida = True
            candidatura.full_clean()
            candidatura.save(update_fields=['excluida'])
        resultado['reservados'] = len(registros_reservados)
        from apps.auditoria.services import registrar_evento
        registrar_evento(accion='escenarios.reservas_autoridad', entidad='Eleccion', entidad_id=eleccion.pk,
            eleccion=eleccion, usuario=usuario, datos_nuevos={'segmento': control['segmento']['carpeta'],
            'documentos_excluidos': sorted(excluidos)})
    elif accion in ('cambios', 'ampliar_cambios'):
        autoridades_antes = list(AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion).order_by('pk').values())
        exigir(solicitudes_cambio_sede_habilitadas(eleccion), 'Publicá la elección y habilitá el plazo de cambios de sede.')
        ampliacion = control.get('ampliacion_solicitudes', [])
        # Ambas acciones cargan el mismo lote; la anterior queda como alias compatible.
        planes = control['solicitudes'] + ampliacion
        exigir(bool(planes), 'No se configuraron personas para las solicitudes.')
        exigir(len({f['dni'] for f in planes}) == len(planes), 'Hay solicitantes repetidos en el escenario.')
        if not ampliacion and not datos.get('conservar_autoridades', False):
            exigir(not AsignacionAutoridad.objects.filter(registro_padron__in=registros_reservados).exists(), 'Un solicitante figura como autoridad.')
            exigir(CandidaturaAutoridad.objects.filter(registro_padron__in=registros_reservados, excluida=True).count() == len(excluidos), 'Ejecutá reservar --aplicar antes de crear solicitudes.')
        registros_solicitantes = {r.elector.dni: r for r in estudiantes if r.es_principal and r.elector.dni in {f['dni'] for f in planes}}
        exigir(len(registros_solicitantes) == len(planes), 'Los solicitantes deben tener un registro principal activo.')
        resultado['solicitantes_con_designacion'] = AsignacionAutoridad.objects.filter(registro_padron__elector_id__in=[r.elector_id for r in registros_solicitantes.values()], registro_padron__eleccion=eleccion).count()
        carga = crear_solicitudes_escenario(eleccion, planes)
        creadas = carga['creadas']
        existentes = Counter(carga['existentes_por_estado'])
        # Incluir a Carlos en la simulación sin crear su solicitud real.
        with transaction.atomic():
            carlos = next(r for r in registros_reservados if r.elector.dni == '38999222')
            if not SolicitudCambioSede.objects.filter(registro_padron=carlos).exists():
                destino = carlos.eleccion_claustro_departamento.sedes_habilitadas.get(sede__nombre='Medrano').sede
                formulario = FormularioSolicitudCambioSede({'sede_destino': destino.pk}, registro_padron=carlos)
                exigir(formulario.is_valid(), str(formulario.errors))
                formulario.save()
            pendientes = SolicitudCambioSede.objects.filter(registro_padron__eleccion=eleccion, estado='pendiente')
            impacto = estimar_impacto_mesas_por_sede(eleccion, pendientes)
            nuevas = sum(impacto['agregadas'].values())
            if creadas:
                minimo = control['configuracion']['ampliacion_cambios'][control['segmento']['carpeta']]['minimo_mesas_nuevas'] if ampliacion else 1
                # Las aprobaciones anteriores pueden haber creado parte de las mesas previstas.
                if existentes.get('aprobada'):
                    minimo = 0
                exigir(minimo <= nuevas <= 9, f'El estado actual produciría {nuevas} mesas nuevas; se revierte el lote para revisar el escenario.')
            transaction.set_rollback(True)
        compartidos = control.get('solicitantes_nomina_pequena', [])
        resultado.update(creadas=len(creadas), solicitudes_del_escenario=len(planes),
            existentes_por_estado=dict(existentes),
            pendientes_totales=SolicitudCambioSede.objects.filter(registro_padron__eleccion=eleccion, estado='pendiente').count(),
            solicitantes_nomina_pequena=compartidos,
            solicitantes_nomina_pequena_designados=AsignacionAutoridad.objects.filter(
                registro_padron__eleccion=eleccion, registro_padron__elector__dni__in=compartidos, estado='asignada').count(),
            impacto_incluyendo_carlos=impacto)
        exigir(autoridades_antes == list(AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion).order_by('pk').values()),
               'Se revierte el lote: cambiaron las designaciones durante la presentación de solicitudes.')
    elif accion == 'justificativos':
        exigir(bool(eleccion.autoridades_confirmadas_en), 'Confirmá las autoridades definitivas antes de presentar justificativos.')
        exigir(not SolicitudCambioSede.objects.filter(registro_padron__eleccion=eleccion, estado='pendiente').exists(), 'Resolvé primero todos los cambios de sede.')
        cuentas_eleccion = Counter(AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion,
            estado='asignada', tipo='titular').values_list('mesa_id', 'turno_id'))
        for ec in eleccion.elecciones_claustro.prefetch_related('turnos_autoridad'):
            mesas = eleccion.mesas.filter(eleccion_claustro_departamento__eleccion_claustro=ec)
            for mesa in mesas:
                for turno in ec.turnos_autoridad.all():
                    exigir(cuentas_eleccion[mesa.pk, turno.turno_id] >= turno.minimo_titulares_por_mesa,
                           'Ya existen vacantes por debajo del mínimo: completalas antes de generar justificativos.')
        exigir(bool(datos.get('tipo')), 'Indicá --tipo con el ID de un tipo de justificativo activo.')
        tipo = TipoJustificativo.objects.get(pk=datos['tipo'], activo=True)
        previos = list(JustificativoAusencia.objects.filter(registro_padron__in=estudiantes, ausencia='autoridad'))
        grupos_usados = set()
        for j in previos:
            aa = AsignacionAutoridad.objects.get(registro_padron=j.registro_padron)
            grupos_usados.add((aa.mesa_id, aa.turno_id))
        necesarios = max(0, control['segmento']['justificativos'] - len(previos))
        autoridades = list(AsignacionAutoridad.objects.filter(registro_padron__in=estudiantes, estado='asignada', tipo='titular').select_related('registro_padron__eleccion').order_by('mesa_id', 'turno_id', 'pk'))
        cuentas = Counter((a.mesa_id, a.turno_id) for a in autoridades)
        formularios = []
        for a in autoridades:
            grupo = (a.mesa_id, a.turno_id)
            if grupo in grupos_usados or cuentas[grupo] <= control['configuracion']['autoridades']['minimo']:
                continue
            f = FormularioJustificativo({'ausencia': 'autoridad', 'tipo': tipo.pk,
                'detalle': 'Caso sintético: imposibilidad de concurrir como autoridad por motivos personales.'}, registro_padron=a.registro_padron)
            exigir(f.is_valid(), str(f.errors))
            formularios.append(f)
            grupos_usados.add(grupo)
            if len(formularios) == necesarios:
                break
        if necesarios == 0:
            formularios = []
        exigir(len(formularios) == necesarios, 'No hay suficientes grupos con tres titulares para generar todo el lote sin afectar el mínimo.')
        for f in formularios:
            f.save()
        resultado.update(creados=len(formularios), existentes=len(previos))
    else:
        exigir(accion == 'verificar', 'Acción desconocida.')
        resultado['mesas'] = eleccion.mesas.count()
        resultado['autoridades'] = AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion).count()
        resultado['reservas_excluidas'] = CandidaturaAutoridad.objects.filter(registro_padron__in=registros_reservados, excluida=True).count()
        resultado['manuales_referencia'] = control['manuales']
    if not datos['aplicar']:
        transaction.set_rollback(True)
    return resultado
