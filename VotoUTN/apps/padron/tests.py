import io
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

from openpyxl import Workbook

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
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro, maximo_votantes_por_mesa=20)
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

    def test_descargar_plantilla_padron_incluye_fila_de_ejemplo(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("descargar-plantilla-padron", args=(self.eleccion.id, self.eleccion_claustro.id)))

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode("utf-8-sig")
        lineas = contenido.splitlines()
        self.assertGreaterEqual(len(lineas), 2)
        self.assertEqual(lineas[0], "DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel")
        self.assertEqual(lineas[1], "40123456,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Si,K,Campus,1")

    def test_validar_csv_padron_mapea_departamento_principal_correctamente(self):
        contenido = (
            "DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n"
            "40123456,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Si,K,Campus,1\n"
        ).encode("utf-8")

        from apps.padron.models import ImportacionPadron
        from apps.padron.services import confirmar_importacion, validar_csv_padron

        validacion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")

        self.assertFalse(validacion.errores)
        self.assertEqual(validacion.filas[0]["departamento_principal"], "K")
        self.assertEqual(validacion.filas[0]["departamento"], "K")

        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile("padron.csv", contenido, content_type="text/csv"),
            nombre_archivo="padron.csv",
            huella_archivo="123",
            usuario=self.usuario,
        )
        importacion.huella_archivo = __import__("hashlib").sha256(contenido).hexdigest()
        importacion.save(update_fields=("huella_archivo",))

        cantidad = confirmar_importacion(importacion)

        self.assertEqual(cantidad, 1)
        elector = importacion.eleccion.registros_padron.get(elector__dni="40123456")
        self.assertEqual(elector.elector.nombre, "Juan")
        self.assertEqual(elector.elector.apellido, "Perez")
        self.assertEqual(elector.elector.departamento_principal, self.departamento)

    def test_validar_csv_padron_acepta_dni_numerico_de_excel(self):
        contenido = (
            "DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n"
            "40123456.0,2024004,Lucia,Diaz,K,lucia.diaz@frba.utn.edu.ar,No,K,Campus,1\n"
        ).encode("utf-8")

        from apps.padron.services import validar_csv_padron

        validacion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")

        self.assertFalse(validacion.errores)
        self.assertEqual(validacion.filas[0]["dni"], "40123456")

    def test_validar_csv_padron_indica_solo_el_legajo_incorrecto(self):
        from apps.padron.models import Elector
        from apps.padron.services import validar_csv_padron

        Elector.objects.create(dni="40123456", legajo="2024999", nombre="Juan", apellido="Perez")
        contenido = (
            "DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,Sede donde asiste\n"
            "40123456,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Campus\n"
        ).encode("utf-8")

        validacion = validar_csv_padron(contenido, self.eleccion_claustro, "padron.csv")

        self.assertIn((2, "legajo", "El legajo no coincide con el elector existente."), validacion.errores)
        self.assertNotIn((2, "dni", "El DNI no coincide con el elector existente."), validacion.errores)

    def test_confirmar_importacion_no_requiere_maximo_por_mesa(self):
        self.eleccion_claustro.maximo_votantes_por_mesa = None
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        contenido = (
            "DNI,Legajo,Nombre,Apellido,Depto/Carrera,Mail,TieneDiscapacidad,Departamento Principal,Sede donde asiste,Nivel\n"
            "40123456,2024001,Juan,Perez,K,juan.perez@frba.utn.edu.ar,Si,K,Campus,1\n"
        ).encode("utf-8")

        from apps.padron.models import ImportacionPadron
        from apps.padron.services import confirmar_importacion

        importacion = ImportacionPadron.objects.create(
            eleccion=self.eleccion,
            eleccion_claustro=self.eleccion_claustro,
            archivo=SimpleUploadedFile("padron.csv", contenido, content_type="text/csv"),
            nombre_archivo="padron.csv",
            huella_archivo="123",
            usuario=self.usuario,
        )
        importacion.huella_archivo = __import__("hashlib").sha256(contenido).hexdigest()
        importacion.save(update_fields=("huella_archivo",))

        cantidad = confirmar_importacion(importacion)

        self.assertEqual(cantidad, 1)
        self.assertEqual(importacion.estado, ImportacionPadron.Estado.CONFIRMADA)


class FormularioArchivoPadronTests(TestCase):
    def test_rechaza_archivo_no_csv_ni_xlsx(self):
        formulario = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.txt", b"contenido")})

        self.assertFalse(formulario.is_valid())

    def test_acepta_archivo_xlsx(self):
        formulario = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.xlsx", b"contenido", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

        self.assertTrue(formulario.is_valid())

    def test_validar_archivo_xlsx_acepta_formato_excel(self):
        libro = Workbook()
        hoja = libro.active
        hoja.append(["DNI", "Legajo", "Nombre", "Apellido", "Depto/Carrera", "Mail", "Sede", "TieneDiscapacidad", "Departamento Principal", "Nivel"])
        hoja.append(["40123456", "2024001", "Juan", "Perez", "Sistemas", "juan.perez@frba.utn.edu.ar", "Campus", "Si", "Ingenieria", "1"])

        archivo = io.BytesIO()
        libro.save(archivo)
        archivo.seek(0)

        respuesta = FormularioArchivoPadron(files={"archivo": SimpleUploadedFile("padron.xlsx", archivo.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        self.assertTrue(respuesta.is_valid())

    def test_confirmar_importacion_xlsx_conserva_el_archivo(self):
        from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, EleccionSede, EleccionTurno
        from apps.padron.models import ImportacionPadron
        from apps.padron.services import confirmar_importacion
        from apps.parametros.models import Claustro, Departamento, Sede, Turno
        from django.contrib.auth import get_user_model
        from django.utils.timezone import make_aware

        ahora = make_aware(datetime(2026, 8, 3, 8))
        eleccion = Eleccion.objects.create(nombre="Eleccion XLSX", fecha_inicio=ahora, fecha_fin=ahora + timedelta(hours=8))
        sede = Sede.objects.create(nombre="Campus XLSX")
        turno = Turno.objects.create(nombre="Manana XLSX", hora_inicio=time(8), hora_fin=time(12))
        claustro = Claustro.objects.create(nombre="Estudiantes XLSX")
        departamento = Departamento.objects.create(nombre="Sistemas XLSX", codigo="KX")
        EleccionSede.objects.create(eleccion=eleccion, sede=sede)
        EleccionTurno.objects.create(eleccion=eleccion, turno=turno)
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro, maximo_votantes_por_mesa=20)
        configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=eleccion_claustro, departamento=departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=configuracion, sede=sede)

        libro = Workbook()
        hoja = libro.active
        hoja.append(["DNI", "Legajo", "Nombre", "Apellido", "Depto/Carrera", "Mail", "Sede"])
        hoja.append(["40123457", "2024007", "Ana", "Perez", "KX", "ana.perez@frba.utn.edu.ar", "Campus XLSX"])
        contenido = io.BytesIO()
        libro.save(contenido)
        contenido.seek(0)
        bytes_archivo = contenido.getvalue()
        usuario = get_user_model().objects.create_user(username="xlsx-confirm", password="clave")
        importacion = ImportacionPadron.objects.create(
            eleccion=eleccion,
            eleccion_claustro=eleccion_claustro,
            archivo=SimpleUploadedFile("padron.xlsx", bytes_archivo),
            nombre_archivo="padron.xlsx",
            huella_archivo=__import__("hashlib").sha256(bytes_archivo).hexdigest(),
            usuario=usuario,
        )

        self.assertEqual(confirmar_importacion(importacion), 1)

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
