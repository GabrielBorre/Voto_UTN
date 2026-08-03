import base64
import hashlib
import hmac
import struct

from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils.timezone import make_aware

from apps.asistencia.models import Asistencia
from apps.asistencia.serializers import SerializadorLoteAsistencia
from apps.asistencia.services import ServicioAsistencia
from apps.elecciones.management.commands.cargar_electores_demo import Command as GeneradorQr
from apps.elecciones.models import (
    Claustro,
    Departamento,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
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
        datos = struct.pack(">HHI", eleccion_id, mesa_numero, legajo)
        firma = hmac.new(
            self.clave_qr.encode("utf-8"),
            datos,
            hashlib.sha256,
        ).digest()[:4]
        return base64.urlsafe_b64encode(datos + firma).decode("ascii").rstrip("=")

    @override_settings(CLAVE_FIRMA_QR=clave_qr)
    def test_acepta_codigo_qr_con_firma_valida(self):
        codigo = self.generar_codigo()

        self.assertEqual(
            ServicioAsistencia._parse_signed_code(codigo),
            (7, 12, "203425"),
        )

    @override_settings(CLAVE_FIRMA_QR=clave_qr)
    def test_rechaza_codigo_qr_con_firma_alterada(self):
        codigo = self.generar_codigo()
        binario = bytearray(base64.urlsafe_b64decode(f"{codigo}=="))
        binario[-1] ^= 1
        alterado = base64.urlsafe_b64encode(binario).decode("ascii").rstrip("=")

        self.assertIsNone(ServicioAsistencia._parse_signed_code(alterado))

    @override_settings(CLAVE_FIRMA_QR="otra-clave")
    def test_rechaza_codigo_qr_firmado_con_otra_clave(self):
        codigo = self.generar_codigo()

        self.assertIsNone(ServicioAsistencia._parse_signed_code(codigo))

    @override_settings(CLAVE_FIRMA_QR=clave_qr)
    def test_el_generador_y_el_validador_comparten_clave_de_firma(self):
        codigo = GeneradorQr().generar_payload_firmado(
            eleccion_id=7,
            mesa_numero=12,
            legajo=203425,
        )

        self.assertEqual(
            ServicioAsistencia._parse_signed_code(codigo),
            (7, 12, "203425"),
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
