from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.asistencia.models import RegistroParticipacion
from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede,
    EleccionClaustroSede, EleccionSede,
)
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import Mesa
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron, SolicitudCambioSede
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol


class GeneradoresDemoTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(
            nombre="Demo", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 30),
        )
        self.sedes = [Sede.objects.create(nombre=nombre) for nombre in ("Campus", "Medrano", "Lugano")]
        claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Estudiantes"),
        )
        self.alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro, departamento=Departamento.objects.create(nombre="Sistemas", codigo="K"),
        )
        for sede in self.sedes:
            EleccionSede.objects.create(eleccion=self.eleccion, sede=sede)
            EleccionClaustroSede.objects.create(eleccion_claustro=claustro, sede=sede)
            EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.alcance, sede=sede)
        self.registros = []
        for indice in range(80):
            elector = Elector.objects.create(
                dni=str(40000000 + indice), legajo=str(indice), nombre="Demo",
                correo_electronico=f"elector{indice}@example.test",
            )
            self.registros.append(RegistroPadron.objects.create(
                elector=elector, eleccion=self.eleccion,
                eleccion_claustro_departamento=self.alcance, sede=self.sedes[0],
            ))

    def test_publicacion_genera_70_y_concentra_al_menos_63_en_una_sede(self):
        self.eleccion.cambiar_estado(Eleccion.Estado.PUBLICADA)
        solicitudes = SolicitudCambioSede.objects.filter(registro_padron__eleccion=self.eleccion)
        self.assertEqual(solicitudes.count(), 70)
        self.assertGreaterEqual(solicitudes.filter(sede_destino=self.sedes[1]).count(), 63)
        self.assertFalse(solicitudes.exclude(estado=SolicitudCambioSede.Estado.PENDIENTE).exists())
        self.assertFalse(JustificativoAusencia.objects.exists())

    def test_publicacion_sin_destino_crea_las_posibles(self):
        EleccionClaustroDepartamentoSede.objects.exclude(sede=self.sedes[0]).delete()
        with self.assertLogs("apps.elecciones.demo_generadores", level="WARNING"):
            self.eleccion.cambiar_estado(Eleccion.Estado.PUBLICADA)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)
        self.assertFalse(SolicitudCambioSede.objects.exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_publicacion_web_crea_solicitudes_y_guarda_el_plazo(self):
        usuario = get_user_model().objects.create_user(username="junta-publicacion")
        AsignacionRol.objects.create(usuario=usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA)
        self.client.force_login(usuario)
        respuesta = self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {
            "estado": "publicada", "fecha_cierre_solicitudes_cambio_sede": "2026-11-30",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, date(2026, 11, 30))
        self.assertEqual(SolicitudCambioSede.objects.count(), 70)

    def test_error_al_generar_revierte_publicacion_y_solicitudes(self):
        with patch("apps.elecciones.demo_generadores.SolicitudCambioSede.save", side_effect=IntegrityError("error")):
            with self.assertRaises(IntegrityError):
                self.eleccion.cambiar_estado(Eleccion.Estado.PUBLICADA)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_PREPARACION)
        self.assertFalse(SolicitudCambioSede.objects.exists())

    def test_comando_solicitudes_usa_sede_electoral_y_no_duplica(self):
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.save(update_fields=("estado",))
        AsignacionSedePadron.objects.create(
            registro_padron=self.registros[0], sede=self.sedes[1], estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        for _ in range(2):
            call_command("generar_solicitudes_cambio_sede_demo", cantidad=80, semilla=3, stdout=StringIO())
        self.assertEqual(SolicitudCambioSede.objects.count(), 80)
        solicitud = SolicitudCambioSede.objects.get(registro_padron=self.registros[0])
        self.assertEqual(solicitud.sede_origen, self.sedes[1])
        self.assertNotEqual(solicitud.sede_destino, solicitud.sede_origen)

    def test_comandos_justificativos_generan_dos_de_cada_y_evitan_duplicados(self):
        self.eleccion.estado = Eleccion.Estado.EN_CURSO
        self.eleccion.save(update_fields=("estado",))
        usuario = get_user_model().objects.create_user(username="junta")
        mesa = Mesa.objects.create(
            eleccion=self.eleccion, eleccion_claustro_departamento=self.alcance, sede=self.sedes[0], numero=1,
        )
        turno = Turno.objects.create(nombre="Mañana", hora_inicio="08:00", hora_fin="12:00")
        TipoJustificativo.objects.create(nombre="Motivo", activo=True)
        for registro in self.registros[:2]:
            RegistroParticipacion.objects.create(registro_padron=registro, mesa=mesa, registrada_por=usuario, metodo="manual")
        for registro in self.registros[2:4]:
            AsignacionAutoridad.objects.create(registro_padron=registro, mesa=mesa, turno=turno, asignada_por=usuario)
        for _ in range(2):
            call_command("generar_justificativos_electores_demo", stdout=StringIO(), stderr=StringIO())
            call_command("generar_justificativos_autoridades_demo", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(JustificativoAusencia.objects.filter(ausencia="votar").count(), 2)
        self.assertEqual(JustificativoAusencia.objects.filter(ausencia="autoridad").count(), 2)
        self.assertEqual(
            set(JustificativoAusencia.objects.filter(ausencia="votar").values_list("registro_padron_id", flat=True)),
            {registro.pk for registro in self.registros[:2]},
        )
        self.assertFalse(JustificativoAusencia.objects.exclude(estado="pendiente").exists())

    def test_comandos_rechazan_eleccion_en_preparacion(self):
        for comando in (
            "generar_solicitudes_cambio_sede_demo", "generar_justificativos_electores_demo",
            "generar_justificativos_autoridades_demo",
        ):
            with self.subTest(comando=comando), self.assertRaises(CommandError):
                call_command(comando, stdout=StringIO())

    def test_justificativos_no_crea_tipo_si_no_hay_catalogo_activo(self):
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.save(update_fields=("estado",))
        usuario = get_user_model().objects.create_user(username="administrador")
        mesa = Mesa.objects.create(
            eleccion=self.eleccion, eleccion_claustro_departamento=self.alcance, sede=self.sedes[0], numero=1,
        )
        RegistroParticipacion.objects.create(
            registro_padron=self.registros[0], mesa=mesa, registrada_por=usuario, metodo="manual",
        )
        with self.assertRaisesMessage(CommandError, "No hay tipos de justificativo activos"):
            call_command("generar_justificativos_electores_demo", stdout=StringIO())
        self.assertFalse(JustificativoAusencia.objects.exists())
        self.assertFalse(TipoJustificativo.objects.exists())
