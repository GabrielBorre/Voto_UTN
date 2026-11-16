from io import StringIO
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.elecciones.forms import FormularioDepartamentosClaustro
from apps.elecciones.models import Eleccion, EleccionClaustro
from apps.justificativos.models import TipoJustificativo
from apps.padron.models import RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido, PuestoEleccion
from apps.usuarios.models import AsignacionRol, PerfilUsuario
from apps.usuarios.permisos import (
    elecciones_con_participacion,
    puede_crear_elecciones,
    puede_registrar_participacion,
    puede_revisar_justificativo,
)


class SeedDemoDataTests(TestCase):
    def test_carga_catalogos_y_casos_electorales_reales_sin_duplicar(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            call_command("seed_demo_data", stdout=StringIO())

            eleccion = Eleccion.objects.get(nombre="Eleccion Demo 2026")
            ids_presentaciones = dict(
                eleccion.partidos_participantes.values_list("codigo_presentacion", "pk")
            )

            self.assertEqual(eleccion.elecciones_claustro.count(), 4)
            self.assertEqual(PuestoEleccion.objects.filter(eleccion_claustro__eleccion=eleccion).count(), 8)
            self.assertEqual(eleccion.partidos_participantes.count(), 10)
            self.assertEqual(ListaCandidatos.objects.filter(participacion__eleccion=eleccion).count(), 18)
            self.assertEqual(Candidato.objects.filter(lista__participacion__eleccion=eleccion).count(), 36)
            self.assertFalse(PuestoEleccion.objects.filter(
                eleccion_claustro__eleccion=eleccion,
                eleccion_claustro__claustro__nombre="No docentes",
                puesto__organo__nombre="Consejo DASUTeN",
            ).exists())
            self.assertFalse(Candidato.objects.filter(lista__participacion__eleccion=eleccion, elector__isnull=True).exists())
            for candidato in Candidato.objects.filter(lista__participacion__eleccion=eleccion).select_related("elector", "lista"):
                candidato.full_clean()
            self.assertEqual(
                eleccion.partidos_participantes.filter(
                    eleccion_claustro__claustro__nombre="Docentes",
                    numero_lista="3",
                ).count(),
                2,
            )
            self.assertTrue(
                eleccion.partidos_participantes.filter(
                    codigo_presentacion="nodocentes-lista-9",
                    nombre_lista="UNIÓN Y PARTICIPACIÓN",
                    apoderado_nombre="Mariano De Luca",
                ).exists()
            )
            self.assertEqual(Sede.objects.count(), 2)
            self.assertEqual(Turno.objects.count(), 3)
            self.assertEqual(Departamento.objects.count(), 10)

            call_command("seed_demo_data", stdout=StringIO())

            self.assertEqual(
                ids_presentaciones,
                dict(eleccion.partidos_participantes.values_list("codigo_presentacion", "pk")),
            )
            self.assertEqual(eleccion.partidos_participantes.count(), 10)
            self.assertEqual(ListaCandidatos.objects.filter(participacion__eleccion=eleccion).count(), 18)
            self.assertEqual(Candidato.objects.filter(lista__participacion__eleccion=eleccion).count(), 36)


class SeedDemoInicialTests(TestCase):
    def test_carga_catalogos_y_usuarios_sin_eleccion_y_es_idempotente(self):
        for _ in range(2):
            call_command("seed_demo_inicial", stdout=StringIO())

        self.assertFalse(Eleccion.objects.exists())
        self.assertFalse(RegistroPadron.objects.exists())
        self.assertEqual(Sede.objects.count(), 2)
        self.assertEqual(Departamento.objects.count(), 10)
        self.assertTrue(TipoJustificativo.objects.filter(nombre="Certificado medico").exists())
        for username, rol in (
            ("juanb", AsignacionRol.Rol.ADMINISTRADOR_JUNTA),
            ("administrativojunta", AsignacionRol.Rol.ADMINISTRATIVO_JUNTA),
        ):
            usuario = get_user_model().objects.get(username=username)
            self.assertFalse(usuario.has_usable_password())
            asignacion = AsignacionRol.objects.get(usuario=usuario, rol=rol)
            asignacion.full_clean()
            self.assertIsNone(asignacion.eleccion)
        self.assertTrue(puede_crear_elecciones(get_user_model().objects.get(username="juanb")))
        self.assertEqual(PerfilUsuario.objects.count(), 2)
        self.assertEqual(AsignacionRol.objects.count(), 2)

    def test_puesto_departamental_se_configura_al_agregar_departamento_despues_de_la_semilla(self):
        call_command("seed_demo_inicial", stdout=StringIO())
        eleccion = Eleccion.objects.create(
            nombre="Nueva elección", fecha_inicio=date(2026, 11, 20), fecha_fin=date(2026, 11, 21),
        )
        claustro = EleccionClaustro.objects.create(
            eleccion=eleccion, claustro=Claustro.objects.get(nombre="Docentes"),
        )
        departamento = Departamento.objects.get(codigo="K")
        formulario = FormularioDepartamentosClaustro(
            data={"departamentos": [departamento.pk]}, eleccion_claustro=claustro,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.guardar()

        puesto = PuestoEleccion.objects.get(
            eleccion_claustro=claustro,
            eleccion_claustro_departamento__departamento=departamento,
            puesto__nombre="Consejero/a departamental",
        )
        self.assertEqual((puesto.cantidad_titulares, puesto.cantidad_suplentes), (5, 5))
        self.assertFalse(Candidato.objects.exists())

    def test_no_asigna_privilegios_a_un_usuario_preexistente_sin_perfil(self):
        usuario = get_user_model().objects.create_user(username="juanb", password="existente")
        with self.assertRaises(CommandError):
            call_command("seed_demo_inicial", stdout=StringIO())
        self.assertFalse(AsignacionRol.objects.filter(usuario=usuario).exists())
        self.assertFalse(Sede.objects.exists())
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("existente"))

    def test_administrador_inicial_puede_operar_en_una_eleccion_posterior(self):
        call_command("seed_demo_inicial", stdout=StringIO())
        usuario = get_user_model().objects.get(username="juanb")
        eleccion = Eleccion.objects.create(
            nombre="Nueva elección", fecha_inicio=date(2026, 11, 20), fecha_fin=date(2026, 11, 21),
            habilitada=True,
        )
        self.assertTrue(puede_registrar_participacion(usuario, eleccion))
        self.assertTrue(puede_revisar_justificativo(usuario, eleccion))
        self.assertIn(eleccion, elecciones_con_participacion(usuario))


class InicioInstanciaDemoTests(SimpleTestCase):
    @patch("apps.elecciones.management.commands.iniciar_instancia_demo.connection")
    @patch("apps.elecciones.management.commands.iniciar_instancia_demo.call_command")
    def test_base_nueva_reintenta_si_falla_y_no_recarga_despues(self, ejecutar, conexion):
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            conexion.introspection.table_names.return_value = []
            ejecutar.side_effect = [None, CommandError("fallo"), None, None, None]
            with self.assertRaises(CommandError):
                call_command("iniciar_instancia_demo", stdout=StringIO())
            marcador = Path(directorio) / ".inicializacion_demo_pendiente"
            self.assertTrue(marcador.exists())
            conexion.introspection.table_names.return_value = ["django_migrations"]
            call_command("iniciar_instancia_demo", stdout=StringIO())
            self.assertFalse(marcador.exists())
            call_command("iniciar_instancia_demo", stdout=StringIO())
            self.assertEqual(
                [llamada.args[0] for llamada in ejecutar.call_args_list],
                ["migrate", "seed_demo_inicial", "migrate", "seed_demo_inicial", "migrate"],
            )

    @patch("apps.elecciones.management.commands.iniciar_instancia_demo.connection")
    @patch("apps.elecciones.management.commands.iniciar_instancia_demo.call_command")
    def test_base_existente_no_se_inicializa(self, ejecutar, conexion):
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            conexion.introspection.table_names.return_value = ["django_migrations"]
            call_command("iniciar_instancia_demo", stdout=StringIO())
            self.assertEqual([llamada.args[0] for llamada in ejecutar.call_args_list], ["migrate"])
