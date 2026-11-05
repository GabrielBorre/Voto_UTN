from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse

from apps.autoridades import tests as base
from apps.autoridades.models import AsignacionAutoridad
from apps.autoridades.services import asignar_autoridad
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.services import calcular_mesas_automaticas_eleccion, recalcular_sedes_y_mesas_claustro


class RecalculoProvisorioTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        self.eleccion_claustro.maximo_votantes_por_mesa = 2
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        self.mesa_2 = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
            generada_automaticamente=True,
        )
        AsignacionMesa.objects.filter(registro_padron__in=self.registros[1:]).update(mesa=self.mesa_2)
        self.conservada, _ = asignar_autoridad(self.registros[0], self.mesa, self.manana, self.usuario)
        self.afectada, _ = asignar_autoridad(self.registros[1], self.mesa_2, self.manana, self.usuario)

    def test_recalcula_sin_eliminar_mesas_y_marca_autoridad_afectada(self):
        resultado = calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario, recalcular_sedes=False, confirmar_afectadas=True)
        self.assertEqual(resultado["autoridades_vacantes"], 1)
        self.assertTrue(Mesa.objects.filter(pk=self.mesa.pk).exists())
        self.assertTrue(Mesa.objects.filter(pk=self.mesa_2.pk).exists())
        self.assertTrue(AsignacionAutoridad.objects.filter(pk=self.conservada.pk).exists())
        self.assertFalse(AsignacionAutoridad.objects.filter(pk=self.afectada.pk).exists())
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa, self.mesa)

    def test_no_libera_autoridades_sin_confirmacion(self):
        with self.assertRaisesMessage(ValueError, "Revisá y confirmá la propuesta"):
            calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario, recalcular_sedes=False)
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa, self.mesa_2)

    def test_recalculo_automatico_informa_designaciones_afectadas(self):
        with patch("apps.padron.services.calcular_asignaciones_sede_claustro", return_value={"asignadas": 3, "pendientes": 0}):
            _sedes, correcto, mensaje = recalcular_sedes_y_mesas_claustro(self.eleccion_claustro, usuario=self.usuario)
        self.assertTrue(correcto)
        self.assertIn("Designaciones provisorias que quedaron vacantes: 1", mensaje)
        self.assertIn(self.registros[1].elector.nombre_completo, mensaje)
        self.assertEqual(AsignacionAutoridad.objects.count(), 1)

    def test_no_recalcula_tras_confirmar_autoridades(self):
        from django.utils import timezone
        self.eleccion.autoridades_confirmadas_en = timezone.now()
        self.eleccion.save(update_fields=("autoridades_confirmadas_en",))
        with self.assertRaisesMessage(ValueError, "autoridades definitivas"):
            calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario, recalcular_sedes=False)
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)

    def test_elimina_mesas_sin_electores_y_libera_sus_autoridades_provisorias(self):
        from apps.padron.models import AsignacionSedePadron
        AsignacionSedePadron.objects.filter(registro_padron__in=self.registros).update(sede=self.sede)
        resultado = calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario,
                                                        recalcular_sedes=False, confirmar_afectadas=True)
        self.assertEqual(resultado["autoridades_vacantes"], 2)
        self.assertEqual(set(resultado["mesas_quitadas"]), {self.mesa.pk, self.mesa_2.pk})
        self.assertFalse(Mesa.objects.filter(pk__in=(self.mesa.pk, self.mesa_2.pk)).exists())
        self.assertFalse(AsignacionAutoridad.objects.exists())
        self.assertTrue(all(a.mesa.sede_id == self.sede.pk for a in AsignacionMesa.objects.select_related("mesa")))

    def test_quita_mesa_sobrante_y_conserva_la_otra(self):
        self.eleccion_claustro.maximo_votantes_por_mesa = 3
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        resultado = calcular_mesas_automaticas_eleccion(self.eleccion, usuario=self.usuario,
                                                        recalcular_sedes=False, confirmar_afectadas=True)
        self.assertEqual(resultado["autoridades_vacantes"], 1)
        self.assertEqual(resultado["mesas_quitadas"], [self.mesa_2.pk])
        self.assertTrue(Mesa.objects.filter(pk=self.mesa.pk).exists())
        self.assertFalse(Mesa.objects.filter(pk=self.mesa_2.pk).exists())

    def test_la_junta_previsualiza_y_confirma_el_recalculo(self):
        self.client.force_login(self.usuario)
        url = reverse("previsualizar-recalculo-mesas", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "1 designaciones provisorias quedarían vacantes")
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa, self.mesa_2)
        respuesta = self.client.post(url, {"propuesta": respuesta.context["propuesta"]})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(AsignacionAutoridad.objects.count(), 1)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa, self.mesa)

    def test_propuesta_obsoleta_no_modifica_asignaciones(self):
        self.client.force_login(self.usuario)
        url = reverse("previsualizar-recalculo-mesas", args=(self.eleccion.pk,))
        propuesta = self.client.get(url).context["propuesta"]
        self.registros[0].nivel = "4"
        self.registros[0].save(update_fields=("nivel",))
        self.client.post(url, {"propuesta": propuesta})
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa, self.mesa_2)
