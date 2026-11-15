from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.demo_generadores import generar_solicitudes_demo
from apps.elecciones.models import (Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionClaustroSede, EleccionSede)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron, SolicitudCambioSede
from apps.padron.solicitudes_escenario import crear_solicitudes_escenario, leer_plan_publicacion
from apps.parametros.models import Claustro, Departamento, Sede, Turno


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SolicitudesPublicacionTests(TestCase):
    def setUp(self):
        self.plan = leer_plan_publicacion()
        hoy = timezone.localdate()
        self.eleccion = Eleccion.objects.create(nombre='Publicación de escenario', fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=10), fecha_cierre_solicitudes_cambio_sede=hoy + timedelta(days=5))
        self.usuario = get_user_model().objects.create_superuser(username='junta-publicacion-19')
        self.sedes = {nombre: Sede.objects.create(nombre=nombre) for nombre in ('Campus', 'Medrano')}
        claustro = Claustro.objects.create(nombre='Estudiantes', abreviatura=self.plan['claustro'])
        ec = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro, maximo_votantes_por_mesa=60)
        for sede in self.sedes.values():
            EleccionSede.objects.create(eleccion=self.eleccion, sede=sede)
            EleccionClaustroSede.objects.create(eleccion_claustro=ec, sede=sede)
        self.alcances, self.mesas = {}, {}
        for numero, codigo in enumerate(('K', 'I'), 1):
            alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=ec,
                departamento=Departamento.objects.create(nombre=codigo, codigo=codigo))
            self.alcances[codigo] = alcance
            for sede in self.sedes.values():
                EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=sede)
            self.mesas[codigo] = Mesa.objects.create(eleccion=self.eleccion, eleccion_claustro_departamento=alcance,
                sede=self.sedes['Campus'], numero=numero, es_especial=codigo == 'I')
        self.principales = {}
        for indice, fila in enumerate(self.plan['solicitudes']):
            elector = Elector.objects.create(dni=fila['dni'], legajo=fila['legajo'], tipo_documento=fila['tipo_documento'],
                nombre=f'Persona {indice}', correo_electronico=f'escenario.{indice}@frba.utn.edu.ar')
            for codigo in fila['departamentos']:
                r = self.crear_registro(elector, codigo, principal=codigo == fila['departamento_principal'])
                if r.es_principal:
                    self.principales[fila['dni']] = r
        self.carlos = self.crear_registro(Elector.objects.create(dni='38999222', legajo='4444443', nombre='Carlos'), 'K')
        for indice, dni in enumerate(self.plan['solicitantes_nomina_pequena']):
            turno = Turno.objects.create(nombre=f'Turno {indice}', hora_inicio='08:00', hora_fin='12:00')
            r = RegistroPadron.objects.get(eleccion=self.eleccion, elector__dni=dni, es_principal=False)
            AsignacionAutoridad.objects.create(registro_padron=r, mesa=self.mesas['I'], turno=turno, asignada_por=self.usuario)

    def crear_registro(self, elector, codigo, *, principal=True):
        r = RegistroPadron.objects.create(elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.alcances[codigo], es_principal=principal)
        AsignacionSedePadron.objects.create(registro_padron=r, sede=self.sedes['Campus'], estado='asignada')
        AsignacionMesa.objects.create(registro_padron=r, mesa=self.mesas[codigo])
        return r

    def test_publicar_carga_las_19_y_conserva_las_tres_autoridades(self):
        autoridades = list(AsignacionAutoridad.objects.order_by('pk').values())
        mesas = list(AsignacionMesa.objects.order_by('pk').values())
        self.eleccion.cambiar_estado('publicada')
        solicitudes = SolicitudCambioSede.objects.all()
        self.assertEqual(solicitudes.count(), 19)
        self.assertEqual(set(solicitudes.values_list('registro_padron__elector__dni', flat=True)), set(self.principales))
        self.assertEqual(set(solicitudes.values_list('estado', flat=True)), {'pendiente'})
        self.assertEqual(solicitudes.filter(registro_padron__elector__dni__in=self.plan['solicitantes_nomina_pequena']).count(), 3)
        self.assertEqual(list(AsignacionAutoridad.objects.order_by('pk').values()), autoridades)
        self.assertEqual(list(AsignacionMesa.objects.order_by('pk').values()), mesas)
        self.assertFalse(solicitudes.filter(registro_padron=self.carlos).exists())

    def test_publicacion_web_utiliza_el_lote_y_guarda_el_plazo(self):
        self.client.force_login(self.usuario)
        limite = (timezone.localdate() + timedelta(days=3)).isoformat()
        respuesta = self.client.post(reverse('cambiar-estado-eleccion', args=(self.eleccion.pk,)),
            {'estado': 'publicada', 'fecha_cierre_solicitudes_cambio_sede': limite})
        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, 'publicada')
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede.isoformat(), limite)
        self.assertEqual(SolicitudCambioSede.objects.count(), 19)

    def test_completa_nueve_faltantes_y_conserva_aprobadas_y_rechazadas(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado='publicada')
        carga = crear_solicitudes_escenario(self.eleccion, self.plan['solicitudes'][:10])
        SolicitudCambioSede.objects.filter(pk=carga['creadas'][0]).update(estado='aprobada', observacion_resolucion='Conservar')
        SolicitudCambioSede.objects.filter(pk=carga['creadas'][1]).update(estado='rechazada', observacion_resolucion='Conservar')
        self.assertEqual(generar_solicitudes_demo(self.eleccion), 9)
        originales = list(SolicitudCambioSede.objects.order_by('pk').values())
        for _ in range(2):
            call_command('generar_solicitudes_cambio_sede_demo', stdout=StringIO())
        self.assertEqual(list(SolicitudCambioSede.objects.order_by('pk').values()), originales)
        self.assertEqual(SolicitudCambioSede.objects.count(), 19)

    def test_padron_incompleto_se_publica_sin_sustitutos_aleatorios(self):
        RegistroPadron.objects.filter(pk=self.principales[self.plan['solicitudes'][0]['dni']].pk).update(activo=False)
        self.eleccion.cambiar_estado('publicada')
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, 'publicada')
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_identidad_distinta_no_se_usa_como_solicitante(self):
        elector = self.principales[self.plan['solicitudes'][0]['dni']].elector
        elector.legajo = 'otro-legajo'
        elector.save(update_fields=['legajo'])
        self.eleccion.cambiar_estado('publicada')
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_actividad_en_un_adicional_revierte_todo_el_lote_y_la_publicacion(self):
        RegistroPadron.objects.filter(eleccion=self.eleccion, elector__dni=self.plan['solicitudes'][-1]['dni'],
            es_principal=False).update(sede=self.sedes['Campus'])
        with self.assertRaises(ValidationError):
            self.eleccion.cambiar_estado('publicada')
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, 'en_preparacion')
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_qr_emitido_revierte_el_lote(self):
        RegistroPadron.objects.filter(pk=self.principales[self.plan['solicitudes'][-1]['dni']].pk).update(qr_generado_en=timezone.now())
        with self.assertRaises(ValidationError):
            self.eleccion.cambiar_estado('publicada')
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_destino_deshabilitado_revierte_el_lote(self):
        self.sedes['Medrano'].activa = False
        self.sedes['Medrano'].save(update_fields=['activa'])
        with self.assertRaises(ValidationError):
            self.eleccion.cambiar_estado('publicada')
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_error_persistiendo_la_ultima_solicitud_revierte_todas(self):
        guardar = SolicitudCambioSede.save
        ultimo = self.principales[self.plan['solicitudes'][-1]['dni']].pk
        def fallar_al_final(solicitud, *args, **kwargs):
            if solicitud.registro_padron_id == ultimo:
                raise IntegrityError('Fallo de prueba')
            return guardar(solicitud, *args, **kwargs)
        with patch.object(SolicitudCambioSede, 'save', fallar_al_final), self.assertRaises(IntegrityError):
            self.eleccion.cambiar_estado('publicada')
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, 'en_preparacion')
        self.assertFalse(SolicitudCambioSede.objects.exists())
