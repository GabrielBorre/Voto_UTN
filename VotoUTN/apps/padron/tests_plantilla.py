import csv
import hashlib
import io
from datetime import time, timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionSede,
)
from apps.padron.models import Elector, ImportacionPadron, RegistroPadron
from apps.padron.services import (
    calcular_mesas_automaticas_eleccion, confirmar_importacion, validar_csv_padron,
)
from apps.parametros.models import Claustro, Departamento, Sede, Turno


class PlantillaPadronTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ahora = timezone.now()
        cls.eleccion = Eleccion.objects.create(
            nombre="Elección plantilla", fecha_inicio=ahora,
            fecha_fin=ahora + timedelta(days=30),
        )
        cls.claustro = EleccionClaustro.objects.create(
            eleccion=cls.eleccion, claustro=Claustro.objects.create(nombre="Estudiantes"),
            maximo_votantes_por_mesa=20,
        )
        campus = Sede.objects.create(nombre="Campus")
        medrano = Sede.objects.create(nombre="Medrano")
        for sede in (campus, medrano):
            EleccionSede.objects.create(eleccion=cls.eleccion, sede=sede)
        for codigo in ("K", "I", "Q", "R"):
            alcance = EleccionClaustroDepartamento.objects.create(
                eleccion_claustro=cls.claustro,
                departamento=Departamento.objects.create(codigo=codigo, nombre=f"Departamento {codigo}"),
            )
            EleccionClaustroDepartamentoSede.objects.create(
                eleccion_claustro_departamento=alcance, sede=campus,
            )
        Turno.objects.create(nombre="Mañana", hora_inicio=time(8), hora_fin=time(12))
        Turno.objects.create(nombre="Noche", hora_inicio=time(18), hora_fin=time(22))
        cls.usuario = get_user_model().objects.create_superuser(username="junta-plantilla")

    def descargar_filas(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse(
            "descargar-plantilla-padron", args=(self.eleccion.pk, self.claustro.pk),
        ))
        self.assertEqual(respuesta.status_code, 200)
        return list(csv.reader(io.StringIO(respuesta.content.decode("utf-8-sig"))))

    def serializar(self, filas, formato):
        if formato == "xlsx":
            libro = Workbook()
            for fila in filas:
                libro.active.append(fila)
            contenido = io.BytesIO()
            libro.save(contenido)
            libro.close()
            return contenido.getvalue()
        contenido = io.StringIO(newline="")
        csv.writer(contenido).writerows(filas)
        return contenido.getvalue().encode("utf-8-sig")

    def test_descripciones_no_se_importan_como_datos_en_csv_y_excel(self):
        filas = self.descargar_filas()
        for formato in ("csv", "xlsx"):
            with self.subTest(formato=formato):
                resultado = validar_csv_padron(
                    self.serializar(filas, formato), self.claustro, f"plantilla.{formato}",
                )
                self.assertTrue(resultado.errores)
                self.assertIn("dni", {campo for _, campo, _ in resultado.errores})
                self.assertFalse(Elector.objects.exists())

    def test_quitar_solo_la_guia_permite_validar_csv_y_excel(self):
        # Conserva la fila de separación vacía de la plantilla.
        filas = self.descargar_filas()[:-1]
        for formato in ("csv", "xlsx"):
            with self.subTest(formato=formato):
                resultado = validar_csv_padron(
                    self.serializar(filas, formato), self.claustro, f"plantilla.{formato}",
                )
                self.assertFalse(resultado.errores, resultado.errores)
                self.assertEqual(len(resultado.filas), 4)
                self.assertEqual(resultado.cantidad_validas, 3)
                self.assertEqual(resultado.cantidad_existentes, 0)
                self.assertTrue(all("Instrucciones" not in fila for fila in resultado.filas))

    def test_columna_auxiliar_con_datos_no_se_descarta_silenciosamente(self):
        filas = [fila + ["Instrucciones" if indice == 0 else ""]
                 for indice, fila in enumerate(self.descargar_filas()[:-1])]
        filas[1][-1] = "No omitir este dato"
        for formato in ("csv", "xlsx"):
            with self.subTest(formato=formato):
                resultado = validar_csv_padron(
                    self.serializar(filas, formato), self.claustro, f"plantilla.{formato}",
                )
                self.assertEqual(len(resultado.errores), 1)
                numero, campo, mensaje = resultado.errores[0]
                self.assertEqual((numero, campo), (2, "archivo"))
                self.assertIn("Instrucciones debe quedar vacía", mensaje)

    def test_archivos_anteriores_con_columna_auxiliar_se_siguen_aceptando(self):
        filas = [fila + ["Instrucciones" if indice == 0 else ""]
                 for indice, fila in enumerate(self.descargar_filas()[:5])]
        for formato in ("csv", "xlsx"):
            with self.subTest(formato=formato):
                resultado = validar_csv_padron(
                    self.serializar(filas, formato), self.claustro, f"plantilla.{formato}",
                )
                self.assertFalse(resultado.errores, resultado.errores)
                self.assertEqual(resultado.cantidad_validas, 3)

    def test_ejemplos_generan_tres_personas_y_una_mesa_especial(self):
        contenido = self.serializar(self.descargar_filas()[:-1], "csv")
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            importacion = ImportacionPadron.objects.create(
                eleccion=self.eleccion, eleccion_claustro=self.claustro,
                usuario=self.usuario, nombre_archivo="plantilla.csv",
                archivo=SimpleUploadedFile("plantilla.csv", contenido),
                huella_archivo=hashlib.sha256(contenido).hexdigest(),
            )
            self.assertEqual(confirmar_importacion(importacion), 3)
            calcular_mesas_automaticas_eleccion(self.eleccion)

        self.assertEqual(Elector.objects.count(), 3)
        self.assertEqual(RegistroPadron.objects.count(), 4)
        registros = RegistroPadron.objects.filter(dni="40000003").select_related(
            "asignacion_mesa__mesa", "eleccion_claustro_departamento__departamento",
        )
        principal = registros.get(es_principal=True)
        adicional = registros.get(es_principal=False)
        self.assertEqual(principal.elector_id, adicional.elector_id)
        self.assertEqual(principal.eleccion_claustro_departamento.departamento.codigo, "Q")
        self.assertEqual(adicional.eleccion_claustro_departamento.departamento.codigo, "R")
        self.assertFalse(principal.asignacion_mesa.mesa.es_especial)
        self.assertTrue(adicional.asignacion_mesa.mesa.es_especial)
        self.assertEqual(principal.asignacion_mesa.mesa.sede_id, adicional.asignacion_mesa.mesa.sede_id)
