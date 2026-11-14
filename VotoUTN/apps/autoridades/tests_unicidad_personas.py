from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.autoridades.distribucion import _resolver_plazas_por_persona, validar_personas_unicas
from apps.autoridades.nomina import identificar_nomina
from apps.padron.models import RegistroPadron


class UnicidadPersonasTests(SimpleTestCase):
    def test_nomina_incluye_registros_de_una_misma_persona_sin_duplicar_identidad(self):
        fila = {"documento": "40123456", "tipo_documento": "DNI", "legajo": ""}
        with patch("apps.autoridades.services.validar_csv_autoridades", return_value=([fila], [])), \
             patch.object(RegistroPadron.objects, "filter") as buscar:
            consulta = buscar.return_value
            consulta.filter.return_value = consulta
            consulta.values_list.return_value = [(1, 10), (2, 10)]
            self.assertEqual(identificar_nomina(object(), b"archivo", "nomina.csv"), [1, 2])

    def test_nomina_rechaza_dos_filas_de_la_misma_persona(self):
        fila = {"documento": "40123456", "tipo_documento": "DNI", "legajo": ""}
        with patch("apps.autoridades.services.validar_csv_autoridades", return_value=([fila, fila], [])), \
             patch.object(RegistroPadron.objects, "filter") as buscar:
            consulta = buscar.return_value
            consulta.filter.return_value = consulta
            consulta.values_list.return_value = [(1, 10), (2, 10)]
            with self.assertRaisesMessage(ValidationError, "más de una vez"):
                identificar_nomina(object(), b"archivo", "nomina.csv")

    def test_rechaza_dos_registros_de_la_misma_persona(self):
        registros = [SimpleNamespace(pk=1, elector_id=10), SimpleNamespace(pk=2, elector_id=10)]
        with self.assertRaisesMessage(ValidationError, "más de un cupo"):
            validar_personas_unicas(registros)

    def test_admite_registros_de_personas_distintas(self):
        registros = [SimpleNamespace(pk=1, elector_id=10), SimpleNamespace(pk=2, elector_id=20)]
        validar_personas_unicas(registros)

    def test_elige_otra_persona_si_un_elector_aparece_en_dos_departamentos(self):
        principal = SimpleNamespace(pk=1, elector_id=10)
        adicional = SimpleNamespace(pk=2, elector_id=10)
        alternativa = SimpleNamespace(pk=3, elector_id=20)
        candidatos = [[(principal, 0), (alternativa, 1)], [(adicional, 0)]]
        for modo in ("nomina", "aleatorio"):
            with self.subTest(modo=modo):
                resultado = _resolver_plazas_por_persona(candidatos, {}, modo=modo, niveles=[0, 0])
                self.assertEqual(resultado, {0: 3, 1: 2})

    def test_conserva_el_registro_fijado_y_no_usa_su_otro_registro(self):
        principal = SimpleNamespace(pk=1, elector_id=10)
        adicional = SimpleNamespace(pk=2, elector_id=10)
        alternativa = SimpleNamespace(pk=3, elector_id=20)
        candidatos = [[(principal, 0)], [(adicional, 0), (alternativa, 1)]]
        for modo in ("nomina", "aleatorio"):
            with self.subTest(modo=modo):
                resultado = _resolver_plazas_por_persona(candidatos, {0: 1}, modo=modo, niveles=[0, 0])
                self.assertEqual(resultado, {0: 1, 1: 3})

    def test_rechaza_dos_asignaciones_fijas_de_la_misma_persona(self):
        principal = SimpleNamespace(pk=1, elector_id=10)
        adicional = SimpleNamespace(pk=2, elector_id=10)
        with self.assertRaisesMessage(ValidationError, "dos cupos"):
            _resolver_plazas_por_persona([[(principal, 0)], [(adicional, 0)]], {0: 1, 1: 2}, modo="nomina", niveles=[0, 0])

    def test_conserva_el_registro_fijo_aunque_otro_registro_tenga_menor_costo(self):
        principal = SimpleNamespace(pk=1, elector_id=10)
        adicional = SimpleNamespace(pk=2, elector_id=10)
        candidatos = [[(principal, 0), (adicional, 1)]]
        resultado = _resolver_plazas_por_persona(candidatos, {0: 2}, modo="nomina", niveles=[0])
        self.assertEqual(resultado, {0: 2})
