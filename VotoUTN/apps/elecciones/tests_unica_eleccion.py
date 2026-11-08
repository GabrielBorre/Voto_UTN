from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.core.exceptions import ValidationError

from apps.elecciones.forms import FormularioEditarEleccion, FormularioEleccion, FormularioPublicarEleccion
from apps.elecciones.models import Eleccion, EleccionSede, EleccionClaustro, EleccionClaustroSede, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, EleccionClaustroTurno
from apps.parametros.models import Claustro, Sede, Departamento, Turno


class EleccionUnicaNoCerradaTests(TestCase):
    def crear_eleccion(self, nombre, estado):
        return Eleccion.objects.create(
            nombre=nombre,
            fecha_inicio=date(2026, 10, 7),
            fecha_fin=date(2026, 10, 8),
            estado=estado,
        )

    def test_no_permite_otra_eleccion_en_cualquier_estado_no_cerrado(self):
        self.crear_eleccion("Eleccion existente", Eleccion.Estado.PUBLICADA)

        for estado in (Eleccion.Estado.EN_PREPARACION, Eleccion.Estado.EN_CURSO):
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
        self.crear_eleccion("Eleccion cerrada 1", Eleccion.Estado.FINALIZADA)
        self.crear_eleccion("Eleccion cerrada 2", Eleccion.Estado.FINALIZADA)
        self.crear_eleccion("Eleccion en borrador", Eleccion.Estado.EN_PREPARACION)

        self.assertEqual(Eleccion.objects.count(), 3)

    def test_fecha_cambio_sede_se_solicita_al_publicar_y_no_al_crear_o_editar(self):
        eleccion = self.crear_eleccion("Eleccion en preparación", Eleccion.Estado.EN_PREPARACION)

        self.assertNotIn("fecha_cierre_solicitudes_cambio_sede", FormularioEleccion().fields)
        self.assertNotIn(
            "fecha_cierre_solicitudes_cambio_sede",
            FormularioEditarEleccion(instance=eleccion).fields,
        )
        formulario_publicacion = FormularioPublicarEleccion(eleccion=eleccion)
        self.assertIn("fecha_cierre_solicitudes_cambio_sede", formulario_publicacion.fields)
        self.assertTrue(formulario_publicacion.fields["fecha_cierre_solicitudes_cambio_sede"].required)

    def test_formulario_editar_muestra_fechas_persistidas_y_no_incluye_plazo_de_autoridades(self):
        eleccion = self.crear_eleccion("Eleccion en preparación", Eleccion.Estado.EN_PREPARACION)
        formulario = FormularioEditarEleccion(instance=eleccion)

        self.assertNotIn("fecha_limite_justificacion_autoridades", formulario.fields)
        self.assertIn('value="2026-10-07"', str(formulario["fecha_inicio"]))
        self.assertIn('value="2026-10-08"', str(formulario["fecha_fin"]))

    def test_formulario_rechaza_crear_otra_eleccion_no_cerrada(self):
        self.crear_eleccion("Eleccion existente", Eleccion.Estado.EN_CURSO)
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

    def test_publicar_requiere_padron_valido_en_todos_los_claustros(self):
        eleccion = self.crear_eleccion("Eleccion configurada", Eleccion.Estado.EN_PREPARACION)
        sede = Sede.objects.create(nombre="Campus")
        claustro = Claustro.objects.create(nombre="Estudiantes")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        turno = Turno.objects.create(nombre="Mañana", hora_inicio="08:00", hora_fin="12:00")
        EleccionSede.objects.create(eleccion=eleccion, sede=sede)
        alcance_claustro = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro)
        EleccionClaustroTurno.objects.create(eleccion_claustro=alcance_claustro, turno=turno)
        EleccionClaustroSede.objects.create(eleccion_claustro=alcance_claustro, sede=sede)
        alcance_departamento = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=alcance_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=alcance_departamento,
            sede=sede,
        )

        with self.assertRaisesMessage(ValidationError, "importación de padrón válida por cada claustro"):
            eleccion.cambiar_estado(Eleccion.Estado.PUBLICADA)