from datetime import date
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.elecciones.forms import FormularioDepartamentosClaustro
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.parametros.models import Claustro, Departamento
from apps.partidos.models import CargoElectivo, OrganoElectivo, PuestoEleccion


class PuestosDepartamentalesPredeterminadosTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(
            nombre="Elección de puestos predeterminados",
            fecha_inicio=date(2026, 11, 1),
            fecha_fin=date(2026, 11, 2),
        )
        self.departamentos = [
            Departamento.objects.create(nombre="Sistemas", codigo="K"),
            Departamento.objects.create(nombre="Ingeniería Civil", codigo="O"),
            Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z"),
            Departamento.objects.create(nombre="Ciencias Basicas", codigo="CB"),
        ]

    def configurar_departamentos(self, nombre_claustro):
        claustro = Claustro.objects.create(nombre=nombre_claustro)
        configuracion = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=claustro,
        )
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [departamento.pk for departamento in self.departamentos]},
            eleccion_claustro=configuracion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()
        return configuracion, formulario

    def test_crea_composicion_por_claustro_y_departamento_y_excluye_ciencias_basicas(self):
        configuraciones = [
            self.configurar_departamentos(nombre)[0]
            for nombre in ("Estudiantes", "Docentes", "Graduados")
        ]
        organo = OrganoElectivo.objects.get(nombre="Consejo Departamental")
        cargo = CargoElectivo.objects.get(
            organo=organo,
            nombre="Consejero/a departamental",
        )
        puestos = PuestoEleccion.objects.filter(
            eleccion_claustro__in=configuraciones,
            puesto=cargo,
        ).select_related("eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento")

        self.assertEqual(puestos.count(), 6)
        cantidades_por_claustro = {
            "Estudiantes": 3,
            "Docentes": 5,
            "Graduados": 2,
        }
        for puesto in puestos:
            cantidad_esperada = cantidades_por_claustro[puesto.eleccion_claustro.claustro.nombre]
            with self.subTest(
                claustro=puesto.eleccion_claustro.claustro.nombre,
                departamento=puesto.eleccion_claustro_departamento.departamento.nombre,
            ):
                self.assertEqual(puesto.cantidad_titulares, cantidad_esperada)
                self.assertEqual(puesto.cantidad_suplentes, cantidad_esperada)
                self.assertNotIn(
                    puesto.eleccion_claustro_departamento.departamento.nombre,
                    ("Ciencias Básicas", "Ciencias Basicas"),
                )

    def test_guardar_repetidamente_no_duplica_ni_reinicia_cantidades(self):
        configuracion, formulario = self.configurar_departamentos("Estudiantes")
        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion,
            eleccion_claustro_departamento__departamento__codigo="K",
        )
        puesto.cantidad_titulares = 4
        puesto.cantidad_suplentes = 4
        puesto.save(update_fields=("cantidad_titulares", "cantidad_suplentes"))

        formulario.guardar()

        self.assertEqual(
            PuestoEleccion.objects.filter(eleccion_claustro=configuracion).count(),
            2,
        )
        puesto.refresh_from_db()
        self.assertEqual(puesto.cantidad_titulares, 4)
        self.assertEqual(puesto.cantidad_suplentes, 4)

    def test_solo_crea_puestos_para_departamentos_recien_agregados(self):
        configuracion, formulario = self.configurar_departamentos("Estudiantes")
        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion,
            eleccion_claustro_departamento__departamento__codigo="K",
        )
        puesto_id = puesto.pk
        puesto.delete()
        nuevo = Departamento.objects.create(nombre="Mecánica", codigo="M")
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [departamento.pk for departamento in self.departamentos] + [nuevo.pk]},
            eleccion_claustro=configuracion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()

        self.assertFalse(PuestoEleccion.objects.filter(pk=puesto_id).exists())
        self.assertFalse(PuestoEleccion.objects.filter(
            eleccion_claustro=configuracion,
            eleccion_claustro_departamento__departamento__codigo="K",
        ).exists())
        nuevo_puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion,
            eleccion_claustro_departamento__departamento=nuevo,
        )
        self.assertEqual((nuevo_puesto.cantidad_titulares, nuevo_puesto.cantidad_suplentes), (3, 3))

    def test_comando_completa_departamentos_existentes_sin_modificar_puestos(self):
        claustro = Claustro.objects.create(nombre="Docentes")
        configuracion = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        for departamento in self.departamentos:
            EleccionClaustroDepartamento.objects.create(
                eleccion_claustro=configuracion, departamento=departamento,
            )
        call_command("habilitar_puestos_departamentales", str(self.eleccion.pk), verbosity=0)
        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion,
            eleccion_claustro_departamento__departamento__codigo="K",
        )
        puesto.cantidad_titulares = 6
        puesto.save(update_fields=("cantidad_titulares",))
        call_command("habilitar_puestos_departamentales", str(self.eleccion.pk), verbosity=0)
        puesto.refresh_from_db()
        self.assertEqual(puesto.cantidad_titulares, 6)
        self.assertEqual(PuestoEleccion.objects.filter(eleccion_claustro=configuracion).count(), 2)

    def test_si_falla_creacion_de_puestos_no_se_guardan_departamentos(self):
        claustro = Claustro.objects.create(nombre="Docentes")
        configuracion = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [self.departamentos[0].pk]}, eleccion_claustro=configuracion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        with patch(
            "apps.partidos.services.habilitar_puestos_departamentales_predeterminados",
            side_effect=ValueError("error de configuración"),
        ):
            with self.assertRaisesMessage(ValueError, "error de configuración"):
                formulario.guardar()
        self.assertFalse(configuracion.departamentos.exists())

    def test_comando_rechaza_eleccion_inexistente(self):
        with self.assertRaisesMessage(CommandError, "No existe la elección"):
            call_command("habilitar_puestos_departamentales", "999999", verbosity=0)

    def test_comando_rechaza_eleccion_que_no_esta_en_preparacion(self):
        self.eleccion.estado = Eleccion.Estado.FINALIZADA
        self.eleccion.save(update_fields=("estado",))

        with self.assertRaisesMessage(CommandError, "en preparación"):
            call_command("habilitar_puestos_departamentales", str(self.eleccion.pk), verbosity=0)

        self.assertFalse(PuestoEleccion.objects.exists())

    def test_no_crea_puestos_departamentales_para_otros_claustros(self):
        self.configurar_departamentos("No docentes")

        self.assertFalse(PuestoEleccion.objects.exists())
