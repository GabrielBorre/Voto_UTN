from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.elecciones.forms import FormularioEleccion
from apps.elecciones.models import Eleccion
from apps.parametros.models import Claustro, Sede


class EleccionUnicaNoCerradaTests(TestCase):
    def crear_eleccion(self, nombre, estado):
        return Eleccion.objects.create(
            nombre=nombre,
            fecha_inicio=date(2026, 10, 7),
            fecha_fin=date(2026, 10, 8),
            estado=estado,
        )

    def test_no_permite_otra_eleccion_en_cualquier_estado_no_cerrado(self):
        self.crear_eleccion("Eleccion existente", Eleccion.Estado.PREPARADA)

        for estado in (Eleccion.Estado.BORRADOR, Eleccion.Estado.ABIERTA):
            with self.subTest(estado=estado):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Eleccion.objects.bulk_create(
                            [
                                Eleccion(
                                    nombre=f"Eleccion {estado}",
                                    fecha_inicio=date(2026, 10, 7),
                                    fecha_fin=date(2026, 10, 8),
                                    estado=estado,
                                ),
                            ]
                        )

    def test_permite_varias_elecciones_cerradas_y_una_no_cerrada(self):
        self.crear_eleccion("Eleccion cerrada 1", Eleccion.Estado.CERRADA)
        self.crear_eleccion("Eleccion cerrada 2", Eleccion.Estado.CERRADA)
        self.crear_eleccion("Eleccion en borrador", Eleccion.Estado.BORRADOR)

        self.assertEqual(Eleccion.objects.count(), 3)

    def test_formulario_rechaza_crear_otra_eleccion_no_cerrada(self):
        self.crear_eleccion("Eleccion existente", Eleccion.Estado.ABIERTA)
        sede = Sede.objects.create(nombre="Sede de prueba")
        claustro = Claustro.objects.create(nombre="Claustro de prueba")
        formulario = FormularioEleccion(
            data={
                "nombre": "Eleccion nueva",
                "fecha_inicio": "2026-10-09",
                "fecha_fin": "2026-10-10",
                "sedes": [sede.pk],
                "claustros": [claustro.pk],
            }
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("Ya existe una elección que no está cerrada", str(formulario.errors))