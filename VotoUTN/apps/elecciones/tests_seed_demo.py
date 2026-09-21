from io import StringIO
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.elecciones.models import Eleccion
from apps.parametros.models import Departamento, Sede, Turno
from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido, PuestoEleccion


class SeedDemoDataTests(TestCase):
    def test_carga_catalogos_y_casos_electorales_reales_sin_duplicar(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            call_command("seed_demo_data", stdout=StringIO())

            eleccion = Eleccion.objects.get(nombre="Eleccion Demo 2026")
            ids_presentaciones = dict(
                eleccion.partidos_participantes.values_list("codigo_presentacion", "pk")
            )

            self.assertEqual(eleccion.elecciones_claustro.count(), 4)
            self.assertEqual(PuestoEleccion.objects.filter(eleccion_claustro__eleccion=eleccion).count(), 9)
            self.assertEqual(eleccion.partidos_participantes.count(), 10)
            self.assertEqual(ListaCandidatos.objects.filter(participacion__eleccion=eleccion).count(), 19)
            self.assertEqual(Candidato.objects.filter(lista__participacion__eleccion=eleccion).count(), 38)
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
            self.assertEqual(ListaCandidatos.objects.filter(participacion__eleccion=eleccion).count(), 19)
            self.assertEqual(Candidato.objects.filter(lista__participacion__eleccion=eleccion).count(), 38)
