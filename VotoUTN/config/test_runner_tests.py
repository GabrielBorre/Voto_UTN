import io
import sys
from datetime import date, datetime

from django.test import SimpleTestCase

from config.corredor_pruebas_excel import (
    COLUMNAS_REPORTE,
    ResultadoPruebasExcel,
    crear_libro_reporte,
    extraer_metadatos_prueba,
)


class PruebaConMetadatos(SimpleTestCase):
    qa_metadata = {
        "Componente Funcional": "Participación",
        "Tester": "Equipo QA",
    }

    def caso_con_docstring(self):
        """Caso de Uso: Registrar participación.
        # Caso de Prueba: QA-QR-001
        Regresión (SI/NO): SI
        Precondiciones: Elección abierta.
        Pasos:
        1. Escanear un QR válido.
        2. Confirmar el registro.
        """


class PruebasCorredorExcelTests(SimpleTestCase):
    def test_docstring_mapea_metadatos_de_prueba(self):
        prueba = PruebaConMetadatos(methodName="caso_con_docstring")
        metadatos = extraer_metadatos_prueba(prueba)

        self.assertEqual(metadatos["Componente Funcional"], "Participación")
        self.assertEqual(metadatos["Tester"], "Equipo QA")
        self.assertEqual(metadatos["Caso de Uso"], "Registrar participación.")
        self.assertEqual(metadatos["# Caso de Prueba"], "QA-QR-001")
        self.assertEqual(metadatos["Regresión (SI/NO)"], "SI")
        self.assertEqual(
            metadatos["Pasos"],
            "1. Escanear un QR válido.\n2. Confirmar el registro.",
        )

    def test_libro_excel_conserva_columnas_y_resultado(self):
        prueba = PruebaConMetadatos(methodName="caso_con_docstring")
        resultado = ResultadoPruebasExcel(
            io.StringIO(),
            descriptions=False,
            verbosity=0,
            fecha_ejecucion=datetime(2026, 10, 13),
        )
        resultado.startTest(prueba)
        try:
            raise AssertionError("resultado de prueba de ejemplo")
        except AssertionError:
            resultado.addFailure(prueba, sys.exc_info())
        resultado.stopTest(prueba)

        registro = resultado.registros_reporte[0]
        self.assertEqual(registro["Resultado"], "FAILED")
        self.assertIn(
            "AssertionError: resultado de prueba de ejemplo",
            registro["Observaciones del Resultado"],
        )
        libro = crear_libro_reporte([registro])
        hoja = libro.active

        self.assertEqual(hoja.max_column, 16)
        self.assertEqual(
            tuple(celda.value for celda in hoja[1]),
            COLUMNAS_REPORTE,
        )
        self.assertEqual(hoja["C2"].value, "QA-QR-001")
        self.assertEqual(hoja["L2"].value, "FAILED")
        self.assertIn("AssertionError: resultado", hoja["O2"].value)
        self.assertEqual(hoja["K2"].value, date(2026, 10, 13))
