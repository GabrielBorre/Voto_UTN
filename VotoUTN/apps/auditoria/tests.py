from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.auditoria.models import EventoAuditoria
from apps.elecciones.models import (
    AsignacionMesa,
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
    RegistroPadron,
    Sede,
    Turno,
)
from apps.usuarios.models import AsignacionRol


class BaseAuditoriaElectoralTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.sede = Sede.objects.create(nombre="Campus")
        self.turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        EleccionTurno.objects.create(eleccion=self.eleccion, turno=self.turno)
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        EleccionClaustroSede.objects.create(eleccion_claustro=self.eleccion_claustro, sede=self.sede)
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=self.departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            turno=self.turno,
        )
        self.usuario = get_user_model().objects.create_user(username="operador", password="clave")

    def crear_padron(self, dni="12345678", legajo="1001"):
        elector = Elector.objects.create(legajo=legajo, nombre="Ana Perez", dni=dni)
        padron = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            activo=True,
        )
        AsignacionMesa.objects.create(registro_padron=padron, mesa=self.mesa)
        return padron


class AuditoriaParticipacionTests(BaseAuditoriaElectoralTests):
    def setUp(self):
        super().setUp()
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=self.eleccion,
        )
        self.eleccion.estado = Eleccion.Estado.ABIERTA
        self.eleccion.habilitada = True
        self.eleccion.save(update_fields=("estado", "habilitada"))

    @override_settings(CLAVE_FIRMA_QR="clave-de-prueba-qr")
    def test_registro_qr_crea_evento_de_auditoria(self):
        padron = self.crear_padron()
        codigo = ServicioRegistroParticipacion.generar_codigo_qr(
            eleccion_id=self.eleccion.id,
            mesa_numero=self.mesa.numero,
            identificador_qr=padron.identificador_qr,
        )

        resultado = ServicioRegistroParticipacion.registrar_lote(
            eleccion=self.eleccion,
            codigos_qr=[codigo],
            usuario=self.usuario,
        )

        participacion = RegistroParticipacion.objects.get()
        evento = EventoAuditoria.objects.get()
        self.assertEqual(resultado.creados, [padron.identificador_qr])
        self.assertEqual(evento.accion, "participacion.registrada_qr")
        self.assertEqual(evento.entidad, "RegistroParticipacion")
        self.assertEqual(evento.entidad_id, str(participacion.id))
        self.assertEqual(evento.eleccion, self.eleccion)
        self.assertEqual(evento.usuario, self.usuario)
        self.assertEqual(evento.datos_nuevos["registro_padron_id"], padron.id)

    def test_registro_manual_crea_evento_de_auditoria(self):
        padron = self.crear_padron()

        resultado = ServicioRegistroParticipacion.registrar_manual(
            eleccion=self.eleccion,
            mesa_numero=self.mesa.numero,
            dni=padron.elector.dni,
            usuario=self.usuario,
        )

        participacion = RegistroParticipacion.objects.get()
        evento = EventoAuditoria.objects.get()
        self.assertEqual(resultado.creados, [padron.identificador_qr])
        self.assertEqual(evento.accion, "participacion.registrada_manual")
        self.assertEqual(evento.entidad_id, str(participacion.id))
        self.assertEqual(evento.datos_nuevos["metodo"], RegistroParticipacion.Metodo.MANUAL)


class AuditoriaEleccionTests(BaseAuditoriaElectoralTests):
    def setUp(self):
        super().setUp()
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(self.usuario)

    def test_cambio_de_estado_crea_evento_de_auditoria(self):
        respuesta = self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.id,)),
            {"estado": Eleccion.Estado.PREPARADA},
            HTTP_HOST="127.0.0.1",
            REMOTE_ADDR="127.0.0.10",
            HTTP_USER_AGENT="Prueba",
        )

        self.assertEqual(respuesta.status_code, 302)
        evento = EventoAuditoria.objects.get()
        self.assertEqual(evento.accion, "eleccion.cambio_estado")
        self.assertEqual(evento.entidad, "Eleccion")
        self.assertEqual(evento.entidad_id, str(self.eleccion.id))
        self.assertEqual(evento.datos_anteriores["estado"], Eleccion.Estado.BORRADOR)
        self.assertEqual(evento.datos_nuevos["estado"], Eleccion.Estado.PREPARADA)
        self.assertEqual(evento.ip, "127.0.0.10")
        self.assertEqual(evento.agente_usuario, "Prueba")
