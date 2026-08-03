import base64
import hashlib
import hmac
import struct
import uuid

from datetime import date, datetime, timedelta, time

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils.timezone import make_aware

from apps.asistencia.models import Asistencia
from apps.asistencia.serializers import SerializadorLoteAsistencia
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.elecciones.management.commands.cargar_electores_demo import Command as GeneradorQr
from apps.elecciones.forms import FormularioAlcanceSedes, FormularioEleccion, FormularioGenerarMesas
from apps.elecciones.models import (
    Claustro,
    Departamento,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    EleccionTurno,
    Elector,
    Mesa,
    Sede,
    Turno,
)
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import puede_administrar_parametros, puede_registrar_participacion


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
                "turnos": [self.turno.id],
            }
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        eleccion = formulario.save()

        self.assertEqual(eleccion.estado, Eleccion.Estado.BORRADOR)
        self.assertFalse(eleccion.habilitada)
        self.assertEqual(eleccion.elecciones_sede.count(), 1)
        self.assertEqual(eleccion.elecciones_claustro.count(), 1)
        self.assertEqual(EleccionClaustroDepartamento.objects.filter(eleccion_claustro__eleccion=eleccion).count(), 0)
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

    def test_calendario_administrativo_exige_orden_del_padron(self):
        inicio = make_aware(datetime(2026, 8, 10, 8))
        eleccion = Eleccion(
            nombre="Eleccion con calendario",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            fecha_apertura_padron_provisorio=date(2026, 8, 5),
            fecha_cierre_padron_provisorio=date(2026, 8, 4),
        )

        with self.assertRaises(ValidationError):
            eleccion.full_clean()


class ParametrosElectoralesTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="gestor", password="clave")
        self.client.force_login(self.usuario)

    def test_administrador_de_junta_puede_crear_y_desactivar_una_sede(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=eleccion,
        )

        self.assertTrue(puede_administrar_parametros(self.usuario))
        respuesta = self.client.post(
            "/gestion/parametros/sedes/nuevo/",
            {"nombre": "Campus", "codigo": "CAM", "activa": "on"},
            HTTP_HOST="127.0.0.1",
        )
        self.assertRedirects(respuesta, "/gestion/parametros/sedes/", fetch_redirect_response=False)
        sede = Sede.objects.get(codigo="CAM")

        respuesta = self.client.post(
            f"/gestion/parametros/sedes/{sede.id}/estado/",
            HTTP_HOST="127.0.0.1",
        )
        self.assertRedirects(respuesta, "/gestion/parametros/sedes/", fetch_redirect_response=False)
        sede.refresh_from_db()
        self.assertFalse(sede.activa)

    def test_usuario_sin_rol_no_accede_a_los_parametros(self):
        respuesta = self.client.get("/gestion/parametros/", HTTP_HOST="127.0.0.1")

        self.assertEqual(respuesta.status_code, 403)


class CicloDeVidaEleccionTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.sede = Sede.objects.create(nombre="Sede A", codigo="SA")
        claustro = Claustro.objects.create(nombre="Docentes", codigo="DOC")
        turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        EleccionTurno.objects.create(eleccion=self.eleccion, turno=turno)
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        EleccionClaustroSede.objects.create(eleccion_claustro=self.eleccion_claustro, sede=self.sede)
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Electronica", codigo="ELE"),
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.turno = turno

    def test_solo_abre_con_mesas_y_cerrar_la_deshabilita(self):
        self.eleccion.cambiar_estado(Eleccion.Estado.PREPARADA)
        with self.assertRaises(ValidationError):
            self.eleccion.cambiar_estado(Eleccion.Estado.ABIERTA)

        Mesa.objects.create(eleccion=self.eleccion, numero=1, eleccion_claustro_departamento=self.configuracion, sede=self.sede, turno=self.turno)
        self.eleccion.cambiar_estado(Eleccion.Estado.ABIERTA)
        self.eleccion.refresh_from_db()
        self.assertTrue(self.eleccion.habilitada)

        self.eleccion.cambiar_estado(Eleccion.Estado.CERRADA)
        self.eleccion.refresh_from_db()
        self.assertFalse(self.eleccion.habilitada)

    def test_no_permite_quitar_una_sede_utilizada_por_mesas(self):
        otra_sede = Sede.objects.create(nombre="Sede B", codigo="SB")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=otra_sede)
        EleccionClaustroSede.objects.create(eleccion_claustro=self.eleccion_claustro, sede=otra_sede)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=otra_sede)
        Mesa.objects.create(eleccion=self.eleccion, numero=1, eleccion_claustro_departamento=self.configuracion, sede=otra_sede, turno=self.turno)

        formulario = FormularioAlcanceSedes(
            data={"sedes": [self.sede.id]},
            eleccion=self.eleccion,
            objeto=self.configuracion,
            tipo="departamento",
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("No se puede quitar", formulario.errors["sedes"][0])
