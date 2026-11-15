"""Prueba de los tres segmentos con servicios reales y base de pruebas PostgreSQL."""
import hashlib
import json
import tempfile
import time
from collections import Counter
from datetime import time as hora, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from generar_escenarios import construir, leer_configuracion
from motor_django import ejecutar
from apps.autoridades.confirmacion import confirmar_autoridades
from apps.autoridades.models import AsignacionAutoridad, ConfiguracionAutoridades
from apps.autoridades.services import asignar_autoridad, redistribuir_autoridades
from apps.autoridades.nomina import identificar_nomina, previsualizar_nomina, confirmar_nomina
from apps.elecciones.models import (Eleccion, EleccionSede, EleccionClaustro, EleccionClaustroSede,
    EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, EleccionClaustroTurno)
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.justificativos.services import resolver_justificativo
from apps.padron.forms import FormularioSolicitudCambioSede
from apps.padron.models import ConfiguracionSedesClaustro, ReglaSedeClaustro, ImportacionPadron, RegistroPadron, SolicitudCambioSede
from apps.padron.services import validar_csv_padron, confirmar_importacion, calcular_mesas_automaticas_eleccion, resolver_solicitud_cambio_sede
from apps.parametros.models import Claustro, Departamento, Sede, Turno


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EscenariosIntegradosTests(TestCase):
    def ejecutar_segmento(self, indice, *, movilidad=False):
        inicio = time.perf_counter()
        c = leer_configuracion()
        s = c['segmentos'][indice]
        archivos = construir(c, s)
        control = json.loads(archivos['control.json'])
        usuario = get_user_model().objects.create_superuser(username='junta-escenarios')
        hoy = timezone.localdate()
        eleccion = Eleccion.objects.create(nombre=s['carpeta'], fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=10),
            fecha_cierre_solicitudes_cambio_sede=hoy + timedelta(days=1))
        sedes = {nombre: Sede.objects.create(nombre=nombre) for nombre in c['sedes']}
        for sede in sedes.values():
            EleccionSede.objects.create(eleccion=eleccion, sede=sede)
        turnos = {nombre: Turno.objects.create(nombre=nombre, hora_inicio=hora(8 + i * 5), hora_fin=hora(13 + i * 5)) for i, nombre in enumerate(c['turnos'])}
        departamentos = {codigo: Departamento.objects.create(codigo=codigo, nombre=codigo) for codigo in [*c['departamentos'], 'Z']}
        ecs = {}
        with tempfile.TemporaryDirectory(prefix='escenarios-media-') as media, override_settings(MEDIA_ROOT=media):
            for cl in s['personas']:
                organizacion = 'sin_departamento' if cl == 'no_docentes' else 'por_departamento'
                ec = EleccionClaustro.objects.create(eleccion=eleccion, claustro=Claustro.objects.create(nombre=cl,
                    abreviatura=c['codigos_claustro'][cl], organizacion_departamentos=organizacion),
                    organizacion_departamentos=organizacion, maximo_votantes_por_mesa=c['maximo_mesa'][cl])
                ecs[cl] = ec
                for turno in turnos.values():
                    EleccionClaustroTurno.objects.create(eleccion_claustro=ec, turno=turno,
                        minimo_titulares_por_mesa=c['autoridades']['minimo'], titulares_por_mesa=c['autoridades']['maximo'])
                habilitadas = [c['sede_electoral'][cl]] if cl in c['sede_electoral'] else c['sedes']
                for nombre in habilitadas:
                    EleccionClaustroSede.objects.create(eleccion_claustro=ec, sede=sedes[nombre])
                codigos = [''] if cl == 'no_docentes' else list(c['departamentos']) + (['Z'] if cl == 'docentes' else [])
                for codigo in codigos:
                    alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=ec, departamento=departamentos.get(codigo))
                    hs = [c['sede_unica_estudiantes'][codigo]] if cl == 'estudiantes' and codigo in c['sede_unica_estudiantes'] else habilitadas
                    for nombre in hs:
                        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=sedes[nombre])
                reglas = ConfiguracionSedesClaustro.objects.create(eleccion_claustro=ec)
                for orden, nombre in enumerate(c['sedes'], 1):
                    ReglaSedeClaustro.objects.create(configuracion=reglas, orden=orden, sede_destino=sedes[nombre],
                        campo='sede_donde_cursa', operador='igual', valor=nombre)
                if cl == 'estudiantes':
                    for orden, nombre, op, valor in [(3, 'Medrano', 'mayor_igual', '4'), (4, 'Campus', 'menor_igual', '3')]:
                        ReglaSedeClaustro.objects.create(configuracion=reglas, orden=orden, sede_destino=sedes[nombre], campo='nivel', operador=op, valor=valor)
                contenido = archivos[f'padron_{cl}.csv']
                resultado = validar_csv_padron(contenido, ec, 'padron.csv')
                self.assertFalse(resultado.errores, resultado.errores[:5])
                imp = ImportacionPadron(eleccion=eleccion, eleccion_claustro=ec, nombre_archivo='padron.csv',
                    huella_archivo=hashlib.sha256(contenido).hexdigest(), usuario=usuario)
                imp.archivo.save(f'{cl}.csv', ContentFile(contenido))
                confirmar_importacion(imp)
            calcular_mesas_automaticas_eleccion(eleccion)
            datos = dict(control=control, eleccion=eleccion.pk, accion='verificar', usuario=usuario.username, tipo=None, aplicar=False)
            ejecutar(datos)
            datos['accion'] = 'reservar'
            ejecutar(datos)
            from apps.autoridades.models import CandidaturaAutoridad
            self.assertFalse(CandidaturaAutoridad.objects.exists())
            datos['aplicar'] = True
            ejecutar(datos)
            ejecutar(datos)
            if movilidad:
                ids = identificar_nomina(ecs['estudiantes'], archivos['nomina_estudiantes_movilidad.csv'], 'nomina_movilidad.csv')
                propuesta = previsualizar_nomina(ecs['estudiantes'], usuario, {'registros': ids, 'mesa': False, 'sede': False, 'votar_mesa': False})
                alternativas = {a['codigo']: a for a in propuesta['alternativas']}
                print(json.dumps({'movilidad': [{k: v for k, v in a.items() if k in
                    ('codigo', 'error', 'titulares', 'titulares_faltantes', 'electores_cambian_mesa',
                     'electores_cambian_sede', 'autoridades_mesa_distinta')} for a in propuesta['alternativas']]}), flush=True)
                self.assertGreater(alternativas['mesa_actual']['titulares_faltantes'], 0)
                self.assertEqual(AsignacionAutoridad.objects.count(), 0, 'La previsualización no debe guardar designaciones.')
                for codigo in ('cambio_sede', 'sede_reacomodo'):
                    alternativa = alternativas[codigo]
                    self.assertNotIn('error', alternativa)
                    self.assertEqual(alternativa['titulares_faltantes'], 0)
                    self.assertGreater(alternativa['electores_cambian_sede'], 0)
                    with transaction.atomic():
                        confirmar_nomina(ecs['estudiantes'], usuario, propuesta, alternativa=codigo)
                        aa = AsignacionAutoridad.objects.filter(mesa__eleccion_claustro_departamento__eleccion_claustro=ecs['estudiantes'], estado='asignada')
                        personas_nomina = RegistroPadron.objects.filter(pk__in=ids).values('elector_id').distinct().count()
                        self.assertEqual(aa.count(), personas_nomina)
                        cuentas = Counter(aa.values_list('mesa_id', 'turno_id'))
                        for mesa in eleccion.mesas.filter(eleccion_claustro_departamento__eleccion_claustro=ecs['estudiantes']):
                            for turno in turnos.values():
                                self.assertGreaterEqual(cuentas[mesa.pk, turno.pk], c['autoridades']['minimo'])
                                self.assertLessEqual(cuentas[mesa.pk, turno.pk], c['autoridades']['maximo'])
                        self.assertFalse(aa.filter(registro_padron__elector__dni__in=[r['dni'] for r in control['solicitudes']] + ['38999222']).exists())
                        transaction.set_rollback(True)
                return
            for propuesta in control['manuales']:
                r = RegistroPadron.objects.get(eleccion=eleccion, elector__dni=propuesta['Documento'],
                    eleccion_claustro_departamento__departamento__codigo=propuesta['departamento'])
                asignar_autoridad(r, r.asignacion_mesa.mesa, turnos[propuesta['turno']], usuario)
            fijas = set(AsignacionAutoridad.objects.values_list('pk', flat=True))
            ConfiguracionAutoridades.objects.create(eleccion_claustro=ecs['estudiantes'], modo='nomina')
            antes = time.perf_counter()
            ids = identificar_nomina(ecs['estudiantes'], archivos['nomina_estudiantes_pequena.csv'], 'nomina.csv')
            propuesta = previsualizar_nomina(ecs['estudiantes'], usuario, {'registros': ids, 'mesa': False, 'sede': False, 'votar_mesa': False})
            confirmar_nomina(ecs['estudiantes'], usuario, propuesta)
            duracion_nomina = time.perf_counter() - antes
            for cl, ec in ecs.items():
                ConfiguracionAutoridades.objects.update_or_create(eleccion_claustro=ec, defaults={'modo': 'aleatorio'})
                redistribuir_autoridades(ec, usuario, preservar_asignaciones=True)
            self.assertTrue(fijas <= set(AsignacionAutoridad.objects.values_list('pk', flat=True)))
            self.validar_minimos(eleccion)
            eleccion.cambiar_estado('publicada')
            designaciones_antes = list(AsignacionAutoridad.objects.order_by('pk').values())
            compartidos = control.get('solicitantes_nomina_pequena', [])
            if compartidos:
                self.assertEqual(AsignacionAutoridad.objects.filter(
                    registro_padron__elector__dni__in=compartidos, estado='asignada').count(), 3)
            datos['accion'] = 'cambios'
            datos['aplicar'] = False
            simulacion = ejecutar(datos)
            esperadas = s['solicitudes'] + len(control.get('ampliacion_solicitudes', []))
            faltantes = 0 if compartidos else esperadas
            self.assertEqual(simulacion['creadas'], faltantes)
            self.assertEqual(SolicitudCambioSede.objects.count(), esperadas - faltantes)
            datos['aplicar'] = True
            if compartidos:
                # Completar las nueve faltantes cuando las diez originales ya existen,
                # incluso si una fue aprobada y ya creó una mesa.
                with transaction.atomic():
                    # Simular una carga parcial solo dentro de la base de pruebas.
                    SolicitudCambioSede.objects.filter(registro_padron__elector__dni__in=[
                        f['dni'] for f in control['ampliacion_solicitudes']]).delete()
                    resolver_solicitud_cambio_sede(SolicitudCambioSede.objects.first(), 'aprobada', usuario)
                    parcial = ejecutar(datos)
                    self.assertEqual(parcial['creadas'], 9)
                    self.assertEqual(parcial['existentes_por_estado'], {'aprobada': 1, 'pendiente': 9})
                    self.assertEqual(SolicitudCambioSede.objects.count(), 19)
                    self.assertEqual(SolicitudCambioSede.objects.filter(estado='aprobada').count(), 1)
                    transaction.set_rollback(True)
            resultado = ejecutar(datos)
            self.assertEqual(resultado['creadas'], faltantes)
            self.assertEqual(ejecutar(datos)['creadas'], 0)
            if compartidos:
                self.assertEqual(resultado['solicitantes_nomina_pequena_designados'], 3)
                self.assertGreaterEqual(sum(resultado['impacto_incluyendo_carlos']['agregadas'].values()), 2)
                self.assertEqual(ejecutar({**datos, 'accion': 'ampliar_cambios'})['creadas'], 0)
                self.assertEqual(list(AsignacionAutoridad.objects.order_by('pk').values()), designaciones_antes)
                # Una solicitud resuelta se conserva al volver a cargar el lote.
                with transaction.atomic():
                    solicitud = SolicitudCambioSede.objects.first()
                    resolver_solicitud_cambio_sede(solicitud, 'aprobada', usuario)
                    resueltas = ejecutar(datos)
                    self.assertEqual(resueltas['creadas'], 0)
                    self.assertEqual(resueltas['existentes_por_estado']['aprobada'], 1)
                    solicitud.refresh_from_db()
                    self.assertEqual(solicitud.estado, 'aprobada')
                    transaction.set_rollback(True)
            self.assertEqual(SolicitudCambioSede.objects.count(), esperadas)
            if compartidos:
                self.client.force_login(usuario)
                revision = self.client.post(f'/gestion/elecciones/{eleccion.pk}/solicitudes-cambio-sede/',
                    {'accion': 'aprobar_todas'})
                self.assertContains(revision, 'Autoridades provisorias afectadas:')
                nombres_compartidos = set(RegistroPadron.objects.filter(eleccion=eleccion,
                    elector__dni__in=compartidos).select_related('elector').values_list('elector__id', flat=True))
                nombres_compartidos = {r.elector.nombre_completo for r in RegistroPadron.objects.filter(
                    eleccion=eleccion, es_principal=True, elector_id__in=nombres_compartidos).select_related('elector')}
                self.assertTrue(nombres_compartidos <= {a['elector'] for a in revision.context['detalle']['autoridades']})
                self.assertGreaterEqual(len(revision.context['detalle']['agregadas']), 2)
                self.assertEqual(list(AsignacionAutoridad.objects.order_by('pk').values()), designaciones_antes)
                self.assertEqual(SolicitudCambioSede.objects.filter(estado='pendiente').count(), esperadas)
            carlos = RegistroPadron.objects.get(eleccion=eleccion, elector__dni='38999222')
            formulario = FormularioSolicitudCambioSede({'sede_destino': sedes['Medrano'].pk}, registro_padron=carlos)
            self.assertTrue(formulario.is_valid(), formulario.errors)
            formulario.save()
            mesas_antes = set(eleccion.mesas.values_list('pk', flat=True))
            for solicitud in SolicitudCambioSede.objects.all():
                resolver_solicitud_cambio_sede(solicitud, 'aprobada', usuario)
            nuevas = set(eleccion.mesas.values_list('pk', flat=True)) - mesas_antes
            self.assertTrue(1 <= len(nuevas) <= 9, len(nuevas))
            calcular_mesas_automaticas_eleccion(eleccion, usuario=usuario, confirmar_afectadas=True)
            for ec in ecs.values():
                redistribuir_autoridades(ec, usuario, preservar_asignaciones=True)
            self.validar_minimos(eleccion)
            # Este guion verifica su propia carga de justificativos. La generación
            # automática al confirmar se cubre en tests_demo_generadores.
            with patch('apps.elecciones.demo_generadores.completar_justificativos_demo', return_value=0):
                confirmar_autoridades(eleccion.pk, usuario, hoy + timedelta(days=3))
            datos['accion'] = 'justificativos'
            datos['tipo'] = TipoJustificativo.objects.create(nombre='Motivos personales').pk
            datos['aplicar'] = False
            ejecutar(datos)
            self.assertFalse(JustificativoAusencia.objects.exists())
            datos['aplicar'] = True
            ejecutar(datos)
            ejecutar(datos)
            self.assertEqual(JustificativoAusencia.objects.count(), s['justificativos'])
            for j in JustificativoAusencia.objects.all():
                resolver_justificativo(j, estado='aprobado', observacion='Revisión de prueba', usuario=usuario)
            self.validar_minimos(eleccion)
            self.assertFalse(JustificativoAusencia.objects.filter(estado='pendiente').exists())
            self.assertFalse(AsignacionAutoridad.objects.filter(registro_padron=carlos).exists())
        print(json.dumps({'segmento': s['carpeta'], 'mesas_nuevas': len(nuevas), 'nomina_segundos': round(duracion_nomina, 3),
                          'total_segundos': round(time.perf_counter() - inicio, 3)}), flush=True)

    def validar_minimos(self, eleccion):
        aa = list(AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion, estado='asignada'))
        cuentas = Counter((a.mesa_id, a.turno_id) for a in aa)
        personas = list(AsignacionAutoridad.objects.filter(registro_padron__eleccion=eleccion, estado='asignada').values_list('registro_padron__elector_id', flat=True))
        self.assertEqual(len(personas), len(set(personas)))
        for mesa in eleccion.mesas.select_related('eleccion_claustro_departamento__eleccion_claustro'):
            for t in mesa.eleccion_claustro_departamento.eleccion_claustro.turnos_autoridad.all():
                self.assertGreaterEqual(cuentas[mesa.pk, t.turno_id], t.minimo_titulares_por_mesa, f'Mesa {mesa.pk}, turno {t.turno_id}')
                self.assertLessEqual(cuentas[mesa.pk, t.turno_id], t.titulares_por_mesa)

    def test_segmento_1(self):
        self.ejecutar_segmento(0)

    def test_segmento_2(self):
        self.ejecutar_segmento(1)

    def test_segmento_3(self):
        self.ejecutar_segmento(2)

    def test_nomina_movilidad(self):
        self.ejecutar_segmento(0, movilidad=True)
