from datetime import datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware
from PIL import Image

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionTurno,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.forms import FormularioArchivoPadron
from apps.padron.management.commands.seed_voters import Command as ComandoGenerarQr
from apps.padron.models import Elector, RegistroPadron
from apps.padron.services import generar_mesas_automaticas
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol


class PadronViewsTests(TestCase):
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
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion)

    def test_previsualizar_padron_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("previsualizar-padron", args=(self.eleccion.id, self.eleccion_claustro.id)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "padron/cargar.html")

    def test_descargar_plantilla_padron_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("descargar-plantilla-padron", args=(self.eleccion.id, self.eleccion_claustro.id)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")


class FormularioArchivoPadronTests(TestCase):
    def test_rechaza_archivo_no_csv(self):
        formulario = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.txt", b"contenido")})

        self.assertFalse(formulario.is_valid())


class ProteccionEmisionQrTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion QR", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8))
        self.sede = Sede.objects.create(nombre="Campus")
        self.turno = Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(13))
        EleccionTurno.objects.create(eleccion=self.eleccion, turno=self.turno)
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes"),
            maximo_votantes_por_mesa=100,
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="K"),
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=1, eleccion_claustro_departamento=self.configuracion,
            sede=self.sede, turno=self.turno, generada_automaticamente=True,
        )
        elector = Elector.objects.create(legajo="1001", dni="12345678", nombre="Ana Pérez")
        self.registro = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion, sede=self.sede,
        )
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=self.mesa)

    def test_generar_qr_marca_emision_y_numero_de_mesa(self):
        with TemporaryDirectory() as directorio, patch.object(
            ComandoGenerarQr,
            "generar_qr",
            return_value=Image.new("RGB", (350, 350), "white"),
        ):
            call_command(
                "seed_voters",
                election_id=self.eleccion.pk,
                configuracion_departamento_id=self.configuracion.pk,
                output=Path(directorio),
            )

        self.registro.refresh_from_db()
        self.assertIsNotNone(self.registro.qr_generado_en)
        self.assertEqual(self.registro.numero_mesa_qr, 1)

    def test_no_regenera_mesas_despues_de_emitir_qr(self):
        self.registro.qr_generado_en = make_aware(datetime(2026, 8, 1, 10))
        self.registro.numero_mesa_qr = 1
        self.registro.save(update_fields=("qr_generado_en", "numero_mesa_qr"))

        with self.assertRaisesMessage(ValueError, "ya se emitieron códigos QR"):
            generar_mesas_automaticas(self.eleccion_claustro)

        self.assertTrue(Mesa.objects.filter(pk=self.mesa.pk).exists())

    def test_bloquea_cambio_directo_de_mesa_despues_de_emitir_qr(self):
        self.registro.qr_generado_en = make_aware(datetime(2026, 8, 1, 10))
        self.registro.numero_mesa_qr = 1
        self.registro.save(update_fields=("qr_generado_en", "numero_mesa_qr"))
        otra_mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, eleccion_claustro_departamento=self.configuracion,
            sede=self.sede, turno=self.turno,
        )
        asignacion = self.registro.asignacion_mesa
        asignacion.mesa = otra_mesa

        with self.assertRaises(ValidationError):
            asignacion.save()

        self.mesa.numero = 3
        with self.assertRaises(ValidationError):
            self.mesa.save()

    def test_falla_de_archivos_no_marca_qr_como_emitido(self):
        with TemporaryDirectory() as directorio, patch.object(
            ComandoGenerarQr,
            "generar_qr",
            return_value=Image.new("RGB", (350, 350), "white"),
        ), patch.object(ComandoGenerarQr, "crear_hojas", side_effect=OSError("sin espacio")):
            with self.assertRaises(OSError):
                call_command(
                    "seed_voters",
                    election_id=self.eleccion.pk,
                    configuracion_departamento_id=self.configuracion.pk,
                    output=Path(directorio),
                )

        self.registro.refresh_from_db()
        self.assertIsNone(self.registro.qr_generado_en)
        self.assertIsNone(self.registro.numero_mesa_qr)
