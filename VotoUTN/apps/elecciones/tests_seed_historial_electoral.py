from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.elecciones.historial_electores import construir_historial_electoral
from apps.elecciones.models import Eleccion
from apps.padron.models import Elector
from apps.parametros.models import Claustro, Departamento, Sede


class SeedHistorialElectoralTests(TestCase):
    def setUp(self):
        self.departamento = Departamento.objects.create(
            nombre="Departamento demo historial",
            codigo="DEMO-HISTORIAL",
        )
        self.sede = Sede.objects.create(nombre="Sede demo historial")
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.elector = Elector.objects.create(
            legajo="DEMO-HISTORIAL-1",
            nombre="Elector",
            apellido="Demo",
            dni="12345678",
            departamento_principal=self.departamento,
        )

    def test_seed_crea_estados_historicos_y_es_idempotente(self):
        call_command("seed_historial_electoral", dni="12345678", stdout=StringIO())

        historial = construir_historial_electoral(self.elector)
        estados_demo = {
            item["estado"]
            for item in historial
            if item["eleccion"].nombre.startswith("[DEMO] Historial electoral")
        }
        self.assertEqual(
            estados_demo,
            {
                "Voto Emitido",
                "Infractor",
                "Pendiente de Revisión",
                "Inasistencia Justificada",
                "Infractor - Justificación Rechazada",
                "En Curso - Voto No Registrado",
            },
        )

        call_command("seed_historial_electoral", dni="12345678", stdout=StringIO())

        elecciones_demo = Eleccion.objects.filter(nombre__startswith="[DEMO] Historial electoral")
        self.assertEqual(elecciones_demo.count(), 6)
        self.assertEqual(self.elector.registros_padron.filter(eleccion__in=elecciones_demo).count(), 6)

    def test_seed_no_crea_registros_si_el_dni_no_existe(self):
        with self.assertRaises(CommandError):
            call_command("seed_historial_electoral", dni="00000000", stdout=StringIO())

        self.assertFalse(Eleccion.objects.filter(nombre__startswith="[DEMO] Historial electoral").exists())
