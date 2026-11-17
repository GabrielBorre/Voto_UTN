from datetime import date

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.elecciones.forms import FormularioDepartamentosClaustro
from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroSede,
    EleccionSede,
)
from apps.elecciones.services import agregar_claustro
from apps.mesas.forms import FormularioGenerarMesas
from apps.padron.services import _configuraciones_por_departamento
from apps.parametros.models import Claustro, Departamento, Sede
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    CupoPuestoClaustro,
    ListaCandidatos,
    NOMBRE_PUESTO_CIENCIAS_BASICAS,
    OrganoElectivo,
    ParticipacionPartido,
    PuestoEleccion,
)


class PuestosGeneradosDesdeParametrosTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(
            nombre="Elección de puestos generados",
            fecha_inicio=date(2026, 11, 1),
            fecha_fin=date(2026, 11, 2),
        )
        self.sistemas = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.civil = Departamento.objects.create(nombre="Ingeniería Civil", codigo="O")
        self.ciencias_basicas = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        organo_departamental = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        organo_directivo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        self.departamental = CargoElectivo.objects.create(
            organo=organo_departamental, nombre="Consejero/a departamental", permite_filtrar_departamentos=True,
        )
        self.de_ciencias_basicas = CargoElectivo.objects.create(
            organo=organo_departamental,
            nombre=NOMBRE_PUESTO_CIENCIAS_BASICAS,
        )
        self.directivo = CargoElectivo.objects.create(organo=organo_directivo, nombre="Consejero/a directivo/a")
        self.estudiantes = Claustro.objects.create(nombre="Estudiantes")
        self.docentes = Claustro.objects.create(nombre="Docentes")
        self.no_docentes = Claustro.objects.create(
            nombre="No docentes", organizacion_departamentos=Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        self.asociar(self.departamental, self.estudiantes, 3, 3)
        self.asociar(self.departamental, self.docentes, 5, 5)
        self.asociar(self.de_ciencias_basicas, self.estudiantes, 2, 2)
        self.asociar(self.directivo, self.estudiantes, 4, 1)
        self.asociar(self.directivo, self.no_docentes, 6, 2)

    def asociar(self, cargo, claustro, titulares, suplentes):
        cargo.claustros_habilitados.add(claustro)
        CupoPuestoClaustro.objects.update_or_create(
            puesto=cargo, claustro=claustro,
            defaults={"cantidad_titulares": titulares, "cantidad_suplentes": suplentes},
        )

    def configurar_departamentos(self, claustro, departamentos):
        configuracion = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [departamento.pk for departamento in departamentos]},
            eleccion_claustro=configuracion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()
        return configuracion

    def puestos(self, configuracion):
        return {
            (
                puesto.puesto.nombre,
                puesto.eleccion_claustro_departamento.departamento.codigo
                if puesto.eleccion_claustro_departamento_id else None,
            ): (puesto.cantidad_titulares, puesto.cantidad_suplentes)
            for puesto in PuestoEleccion.objects.filter(eleccion_claustro=configuracion).select_related(
                "puesto", "eleccion_claustro_departamento__departamento",
            )
        }

    def crear_lista(self, puesto):
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="LISTA-1", eleccion_claustro=puesto.eleccion_claustro,
            numero_lista="1", nombre_lista="Lista",
        )
        return ListaCandidatos.objects.create(
            participacion=participacion, eleccion_claustro=puesto.eleccion_claustro,
            eleccion_claustro_departamento=puesto.eleccion_claustro_departamento,
            nombre="Lista", puesto_eleccion=puesto,
        )

    def test_departamental_genera_uno_por_departamento_y_general_uno_por_claustro(self):
        configuracion = self.configurar_departamentos(
            self.estudiantes, [self.sistemas, self.civil, self.ciencias_basicas],
        )

        self.assertEqual(self.puestos(configuracion), {
            ("Consejero/a departamental", "K"): (3, 3),
            ("Consejero/a departamental", "O"): (3, 3),
            ("Consejero/a departamental", "Z"): (3, 3),
            (NOMBRE_PUESTO_CIENCIAS_BASICAS, None): (2, 2),
            ("Consejero/a directivo/a", None): (4, 1),
        })

    def test_departamento_especifico_heredado_no_limita_ni_excluye_puestos(self):
        anterior = CargoElectivo.objects.create(
            organo=self.departamental.organo, nombre="Puesto anterior",
            permite_filtrar_departamentos=True, departamento=self.ciencias_basicas,
        )
        self.asociar(anterior, self.docentes, 2, 2)

        configuracion = self.configurar_departamentos(self.docentes, [self.sistemas, self.ciencias_basicas])

        self.assertEqual(self.puestos(configuracion), {
            ("Consejero/a departamental", "K"): (5, 5),
            ("Consejero/a departamental", "Z"): (5, 5),
            ("Puesto anterior", "K"): (2, 2),
            ("Puesto anterior", "Z"): (2, 2),
        })
        anterior.refresh_from_db()
        self.assertEqual(anterior.departamento_id, self.ciencias_basicas.id)

    def test_claustro_sin_departamentos_recibe_solo_puestos_generales(self):
        self.asociar(self.departamental, self.no_docentes, 1, 1)
        configuracion = agregar_claustro(self.eleccion, self.no_docentes)

        self.assertEqual(self.puestos(configuracion), {("Consejero/a directivo/a", None): (6, 2)})

    def test_agregar_claustro_genera_sus_puestos_generales(self):
        configuracion = agregar_claustro(self.eleccion, self.estudiantes)

        self.assertEqual(self.puestos(configuracion), {
            ("Consejero/a directivo/a", None): (4, 1),
            (NOMBRE_PUESTO_CIENCIAS_BASICAS, None): (2, 2),
        })

    def test_guardar_repetidamente_no_duplica_ni_reinicia_estado(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas])
        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion, eleccion_claustro_departamento__departamento=self.sistemas,
        )
        puesto.activo = False
        puesto.save(update_fields=("activo",))

        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [self.sistemas.pk]}, eleccion_claustro=configuracion,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()

        self.assertEqual(PuestoEleccion.objects.filter(eleccion_claustro=configuracion).count(), 3)
        puesto.refresh_from_db()
        self.assertFalse(puesto.activo)

    def test_cambiar_los_cupos_actualiza_las_elecciones_en_preparacion(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas])
        self.asociar(self.departamental, self.estudiantes, 6, 2)

        call_command("sincronizar_puestos_eleccion", str(self.eleccion.pk), verbosity=0)

        self.assertEqual(self.puestos(configuracion)[("Consejero/a departamental", "K")], (6, 2))

    def test_no_reduce_cupos_por_debajo_de_las_candidaturas_cargadas(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas])
        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion, eleccion_claustro_departamento__departamento=self.sistemas,
        )
        lista = self.crear_lista(puesto)
        Candidato.objects.create(
            lista=lista, nombre="Ana", dni="1", cargo="Consejero/a", tipo=Candidato.Tipo.TITULAR, orden=3,
        )
        self.asociar(self.departamental, self.estudiantes, 2, 2)

        call_command("sincronizar_puestos_eleccion", str(self.eleccion.pk), verbosity=0)

        puesto.refresh_from_db()
        self.assertEqual((puesto.cantidad_titulares, puesto.cantidad_suplentes), (3, 3))

    def test_desasociar_un_claustro_retira_los_puestos_sin_listas_y_conserva_los_usados(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas, self.civil])
        usado = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion, eleccion_claustro_departamento__departamento=self.sistemas,
        )
        self.crear_lista(usado)
        self.departamental.claustros_habilitados.remove(self.estudiantes)
        self.departamental.cupos_claustro.filter(claustro=self.estudiantes).delete()

        call_command("sincronizar_puestos_eleccion", str(self.eleccion.pk), verbosity=0)

        self.assertEqual(self.puestos(configuracion), {
            ("Consejero/a departamental", "K"): (3, 3),
            ("Consejero/a directivo/a", None): (4, 1),
            (NOMBRE_PUESTO_CIENCIAS_BASICAS, None): (2, 2),
        })

    def test_quitar_un_departamento_retira_sus_puestos_sin_listas(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas, self.civil])
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [self.sistemas.pk]}, eleccion_claustro=configuracion,
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()

        self.assertEqual(self.puestos(configuracion), {
            ("Consejero/a departamental", "K"): (3, 3),
            ("Consejero/a directivo/a", None): (4, 1),
            (NOMBRE_PUESTO_CIENCIAS_BASICAS, None): (2, 2),
        })

    def test_quitar_un_departamento_con_listas_se_rechaza(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas, self.civil])
        self.crear_lista(PuestoEleccion.objects.get(
            eleccion_claustro=configuracion, eleccion_claustro_departamento__departamento=self.civil,
        ))
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [self.sistemas.pk]}, eleccion_claustro=configuracion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("listas", str(formulario.errors))

    def test_elecciones_que_no_estan_en_preparacion_no_se_modifican(self):
        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas])
        self.eleccion.estado = Eleccion.Estado.FINALIZADA
        self.eleccion.save(update_fields=("estado",))
        self.asociar(self.departamental, self.estudiantes, 9, 9)

        with self.assertRaisesMessage(CommandError, "en preparación"):
            call_command("sincronizar_puestos_eleccion", str(self.eleccion.pk), verbosity=0)
        call_command("sincronizar_puestos_eleccion", verbosity=0)

        self.assertEqual(self.puestos(configuracion)[("Consejero/a departamental", "K")], (3, 3))

    def test_formulario_de_puesto_rechaza_reducir_cupos_por_debajo_de_las_candidaturas(self):
        from apps.partidos.forms import FormularioCargoElectivo

        configuracion = self.configurar_departamentos(self.estudiantes, [self.sistemas])
        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=configuracion, eleccion_claustro_departamento__departamento=self.sistemas,
        )
        Candidato.objects.create(
            lista=self.crear_lista(puesto), nombre="Ana", dni="1", cargo="Consejero/a",
            tipo=Candidato.Tipo.TITULAR, orden=3,
        )

        def datos(titulares, suplentes):
            return {
                "organo": self.departamental.organo_id, "nombre": self.departamental.nombre,
                "tipo_alcance": "departamental", "activo": "on",
                f"claustro_{self.estudiantes.pk}": "on",
                f"titulares_{self.estudiantes.pk}": str(titulares),
                f"suplentes_{self.estudiantes.pk}": str(suplentes),
            }

        rechazado = FormularioCargoElectivo(datos(2, 3), instance=self.departamental)
        self.assertFalse(rechazado.is_valid())
        self.assertIn(f"titulares_{self.estudiantes.pk}", rechazado.errors)

        aceptado = FormularioCargoElectivo(datos(3, 4), instance=self.departamental)
        self.assertTrue(aceptado.is_valid(), aceptado.errors)
        aceptado.save()

        puesto.refresh_from_db()
        self.assertEqual((puesto.cantidad_titulares, puesto.cantidad_suplentes), (3, 4))
        self.assertFalse(self.departamental.claustros_habilitados.filter(pk=self.docentes.pk).exists())

    def test_comando_rechaza_eleccion_inexistente(self):
        with self.assertRaisesMessage(CommandError, "No existe la elección"):
            call_command("sincronizar_puestos_eleccion", "999999", verbosity=0)

    def test_formulario_ofrece_ciencias_basicas_como_departamento_del_claustro(self):
        configuracion = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.estudiantes)
        sede = Sede.objects.create(nombre="Campus")
        EleccionClaustroSede.objects.create(eleccion_claustro=configuracion, sede=sede)

        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [self.ciencias_basicas.pk]}, eleccion_claustro=configuracion,
        )
        self.assertIn(self.ciencias_basicas, list(formulario.fields["departamentos"].queryset))
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()

        alcance = configuracion.departamentos.get(departamento=self.ciencias_basicas)
        self.assertFalse(alcance.solo_puesto_electivo)
        self.assertTrue(alcance.sedes_habilitadas.filter(sede=sede).exists())
        self.assertIn("z", _configuraciones_por_departamento(configuracion))
        self.assertEqual(
            self.puestos(configuracion)[("Consejero/a departamental", "Z")], (3, 3),
        )

    def test_alcance_exclusivo_heredado_se_habilita_como_departamento_ordinario(self):
        configuracion = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.estudiantes)
        sede = Sede.objects.create(nombre="Campus")
        EleccionClaustroSede.objects.create(eleccion_claustro=configuracion, sede=sede)
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=configuracion, departamento=self.ciencias_basicas, solo_puesto_electivo=True,
        )
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [self.ciencias_basicas.pk]}, eleccion_claustro=configuracion,
        )
        self.assertEqual(list(formulario.fields["departamentos"].initial), [])
        self.assertTrue(formulario.is_valid(), formulario.errors)

        formulario.guardar()

        alcance.refresh_from_db()
        self.assertFalse(alcance.solo_puesto_electivo)
        self.assertEqual(configuracion.departamentos.count(), 1)
        self.assertTrue(alcance.sedes_habilitadas.filter(sede=sede).exists())

    def test_alcance_exclusivo_heredado_no_habilita_sedes_padron_ni_mesas(self):
        sede = Sede.objects.create(nombre="Campus")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=sede)
        configuracion = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.estudiantes)
        EleccionClaustroSede.objects.create(eleccion_claustro=configuracion, sede=sede)
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=configuracion, departamento=self.ciencias_basicas, solo_puesto_electivo=True,
        )

        self.eleccion.validar_configuracion(validar_turnos=False)

        self.assertNotIn("z", _configuraciones_por_departamento(configuracion))
        self.assertNotIn(
            alcance, list(FormularioGenerarMesas(eleccion=self.eleccion).fields["configuracion"].queryset),
        )
