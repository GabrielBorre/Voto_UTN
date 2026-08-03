import base64
import hashlib
import hmac
import struct
import uuid

from datetime import datetime, timedelta, time

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils.timezone import make_aware

from apps.asistencia.models import Asistencia
from apps.asistencia.serializers import SerializadorLoteAsistencia
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.elecciones.management.commands.cargar_electores_demo import Command as GeneradorQr
from apps.elecciones.forms import FormularioEleccion, FormularioGenerarMesas
from apps.elecciones.models import (
    Claustro,
    Departamento,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionTurno,
    Elector,
    Mesa,
    Sede,
    Turno,
)
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import puede_registrar_participacion


class ServicioAsistenciaQrTests(SimpleTestCase):
    clave_qr = "clave-de-prueba-qr"

    def generar_codigo(self, *, eleccion_id=7, mesa_numero=12, legajo=203425):
        return ServicioRegistroParticipacion.generar_codigo_qr(
            eleccion_id=eleccion_id,
            mesa_numero=mesa_numero,
            identificador_qr=uuid.UUID(int=legajo),
        )

    @override_settings(CLAVE_FIRMA_QR=clave_qr)
    def test_acepta_codigo_qr_con_firma_valida(self):
        codigo = self.generar_codigo()

        self.assertEqual(
            ServicioRegistroParticipacion.parsear_codigo_qr(codigo),
            (7, 12, uuid.UUID(int=203425).hex),
        )

    @override_settings(CLAVE_FIRMA_QR=clave_qr)
    def test_rechaza_codigo_qr_con_firma_alterada(self):
        codigo = self.generar_codigo()
        version, contenido = codigo.split(".")
        binario = bytearray(base64.urlsafe_b64decode(contenido + "=" * (-len(contenido) % 4)))
        binario[-1] ^= 1
        alterado = f"{version}.{base64.urlsafe_b64encode(binario).decode('ascii').rstrip('=')}"

        self.assertIsNone(ServicioRegistroParticipacion.parsear_codigo_qr(alterado))

    def test_rechaza_codigo_qr_firmado_con_otra_clave(self):
        with override_settings(CLAVE_FIRMA_QR=self.clave_qr):
            codigo = self.generar_codigo()

        with override_settings(CLAVE_FIRMA_QR="otra-clave"):
            self.assertIsNone(ServicioRegistroParticipacion.parsear_codigo_qr(codigo))

    @override_settings(CLAVE_FIRMA_QR=clave_qr)
    def test_el_generador_y_el_validador_comparten_clave_de_firma(self):
        codigo = self.generar_codigo()

        self.assertEqual(
            ServicioRegistroParticipacion.parsear_codigo_qr(codigo),
            (7, 12, uuid.UUID(int=203425).hex),
        )


class NomenclaturaDominioTests(SimpleTestCase):
    def test_los_modelos_exponen_campos_de_dominio_en_espanol(self):
        self.assertIsNotNone(Eleccion._meta.get_field("nombre"))
        self.assertIsNotNone(Eleccion._meta.get_field("fecha_inicio"))
        self.assertIsNotNone(Elector._meta.get_field("nombre"))
        self.assertIsNotNone(Asistencia._meta.get_field("codigo_elector"))
        self.assertIsNotNone(Asistencia._meta.get_field("registrada_por"))

    def test_el_serializador_recibe_codigos_qr(self):
        serializador = SerializadorLoteAsistencia(data={"codigos_qr": ["codigo-demo"]})

        self.assertTrue(serializador.is_valid(), serializador.errors)
        self.assertEqual(serializador.validated_data["codigos_qr"], ["codigo-demo"])


class ModeloElectoralTests(TestCase):
    def test_turno_rechaza_un_horario_invalido(self):
        turno = Turno(nombre="Mañana", hora_inicio=time(12), hora_fin=time(8))

        with self.assertRaises(ValidationError):
            turno.clean()

    def test_mesa_y_padron_deben_corresponder_a_la_misma_eleccion(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        fin = make_aware(datetime(2026, 8, 3, 18))
        eleccion = Eleccion.objects.create(nombre="Elección 1", fecha_inicio=inicio, fecha_fin=fin)
        otra_eleccion = Eleccion.objects.create(nombre="Elección 2", fecha_inicio=inicio, fecha_fin=fin)
        claustro = Claustro.objects.create(nombre="Estudiantes", codigo="E")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro),
            departamento=departamento,
        )
        sede = Sede.objects.create(nombre="Sede Central", codigo="SC")
        mesa = Mesa(eleccion=otra_eleccion, numero=1, eleccion_claustro_departamento=configuracion, sede=sede)

        with self.assertRaises(ValidationError):
            mesa.clean()


class PermisosParticipacionTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        fin = make_aware(datetime(2026, 8, 3, 18))
        self.eleccion = Eleccion.objects.create(nombre="Elección", fecha_inicio=inicio, fecha_fin=fin)
        self.usuario = get_user_model().objects.create_user(username="operador", password="clave")

    def test_administrativo_asignado_puede_registrar_en_su_eleccion(self):
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=self.eleccion,
        )

        self.assertTrue(puede_registrar_participacion(self.usuario, self.eleccion))

    def test_autoridad_de_mesa_no_puede_registrar_participacion(self):
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=self.eleccion,
        )

        self.assertFalse(puede_registrar_participacion(self.usuario, self.eleccion))


class GestionEleccionesTests(TestCase):
    def setUp(self):
        self.sede = Sede.objects.create(nombre="Sede Central", codigo="SC")
        self.claustro = Claustro.objects.create(nombre="Estudiantes", codigo="EST")
        self.turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))

    def test_formulario_crea_la_configuracion_inicial_de_la_eleccion(self):
        formulario = FormularioEleccion(
            data={
                "nombre": "Eleccion de prueba",
                "fecha_inicio": "2026-08-03T08:00",
                "fecha_fin": "2026-08-03T18:00",
                "estado": Eleccion.Estado.PREPARADA,
                "habilitada": "on",
                "sedes": [self.sede.id],
                "claustros": [self.claustro.id],
                "departamentos": [Departamento.objects.create(nombre="Sistemas", codigo="SIS").id],
                "turnos": [self.turno.id],
            }
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        eleccion = formulario.save()

        self.assertEqual(eleccion.elecciones_sede.count(), 1)
        self.assertEqual(eleccion.elecciones_claustro.count(), 1)
        self.assertEqual(EleccionClaustroDepartamento.objects.filter(eleccion_claustro__eleccion=eleccion).count(), 1)
        self.assertTrue(EleccionTurno.objects.filter(eleccion=eleccion, turno=self.turno).exists())

    def test_generacion_crea_mesas_numeradas_y_valida_turno_habilitado(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        EleccionSede.objects.create(eleccion=eleccion, sede=self.sede)
        claustro_eleccion = EleccionClaustro.objects.create(eleccion=eleccion, claustro=self.claustro)
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_eleccion,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="SIS"),
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=configuracion,
            sede=self.sede,
        )
        EleccionTurno.objects.create(eleccion=eleccion, turno=self.turno)

        formulario = FormularioGenerarMesas(
            eleccion=eleccion,
            data={"configuracion": configuracion.id, "sede": self.sede.id, "turno": self.turno.id, "cantidad": 2},
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.generar()
        self.assertEqual(list(eleccion.mesas.values_list("numero", flat=True)), [1, 2])

        turno_ajeno = Turno.objects.create(nombre="Tarde", hora_inicio=time(13), hora_fin=time(18))
        mesa = Mesa(eleccion=eleccion, numero=3, eleccion_claustro_departamento=configuracion, sede=self.sede, turno=turno_ajeno)
        with self.assertRaises(ValidationError):
            mesa.full_clean()
