from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.autoridades import tests as base
from apps.autoridades.distribucion import distribuir, reacomodar_titulares
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades
from apps.autoridades.services import confirmar_cambio_sede_para_autoridad
from apps.mesas.models import AsignacionMesa, Mesa


class TrasladosLaboralesTests(TestCase):
    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        self.opciones = ConfiguracionAutoridades.objects.create(
            eleccion_claustro=self.eleccion_claustro, permitir_cambio_sede=True,
        )
        self.destino = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sede,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
        )
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, suplentes_por_mesa=0)
        for registro in self.registros:
            CandidaturaAutoridad.objects.create(registro_padron=registro, cargada_por=self.usuario)
        distribuir(self.eleccion_claustro, self.usuario)

    def test_traslado_cubre_vacante_sin_modificar_padron_y_revalida(self):
        registro = next(r for r in self.registros if not AsignacionAutoridad.objects.filter(registro_padron=r).exists())
        confirmar_cambio_sede_para_autoridad(registro, self.sede, self.usuario, mesa=self.destino, turno=self.manana)
        registro.refresh_from_db()
        self.assertEqual(registro.asignacion_mesa.mesa_id, self.mesa.pk)
        self.assertEqual(registro.asignacion_sede_padron.sede_id, self.sede_votacion.pk)
        self.assertEqual(AsignacionAutoridad.objects.get(registro_padron=registro).mesa_id, self.destino.pk)
        self.assertEqual(AsignacionAutoridad.objects.filter(mesa=self.mesa).count(), 1)
        otro = next(r for r in self.registros if not AsignacionAutoridad.objects.filter(registro_padron=r).exists())
        with self.assertRaisesMessage(ValidationError, "vacante"):
            confirmar_cambio_sede_para_autoridad(otro, self.sede, self.usuario, mesa=self.destino, turno=self.manana)

    def test_traslado_deshabilitado_no_modifica_nada(self):
        self.opciones.permitir_cambio_sede = False
        self.opciones.save()
        with self.assertRaisesMessage(ValidationError, "habilitados"):
            confirmar_cambio_sede_para_autoridad(self.registros[1], self.sede, self.usuario, mesa=self.destino, turno=self.manana)
        self.assertFalse(CandidaturaAutoridad.objects.filter(mesa_traslado__isnull=False).exists())

    def test_desactivar_traslados_conserva_asignacion_ya_confirmada(self):
        registro = next(r for r in self.registros if not AsignacionAutoridad.objects.filter(registro_padron=r).exists())
        confirmar_cambio_sede_para_autoridad(registro, self.sede, self.usuario, mesa=self.destino, turno=self.manana)
        self.opciones.permitir_cambio_sede = False
        self.opciones.save()
        distribuir(self.eleccion_claustro, self.usuario)
        self.assertTrue(CandidaturaAutoridad.objects.filter(registro_padron=registro, mesa_traslado=self.destino).exists())
        self.assertTrue(AsignacionAutoridad.objects.filter(registro_padron=registro, mesa=self.destino).exists())
        self.assertTrue(AsignacionAutoridad.objects.filter(mesa=self.mesa).exists())
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=registro).mesa_id, self.mesa.pk)

    def test_reacomodo_no_cambia_sede_electoral_del_traslado(self):
        registro = next(r for r in self.registros if not AsignacionAutoridad.objects.filter(registro_padron=r).exists())
        self.opciones.reacomodar_titulares = True
        self.opciones.save()
        confirmar_cambio_sede_para_autoridad(registro, self.sede, self.usuario, mesa=self.destino, turno=self.manana)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=registro).mesa_id, self.mesa.pk)

    def test_reacomodo_no_desplaza_suplentes_y_revierte_sin_capacidad(self):
        # Dos mesas llenas: un titular quiere entrar donde solo hay suplentes.
        self.destino.sede = self.sede_votacion
        self.destino.save()
        self.eleccion_claustro.maximo_votantes_por_mesa = 1
        self.eleccion_claustro.save()
        AsignacionMesa.objects.filter(registro_padron=self.registros[2]).delete()
        AsignacionMesa.objects.filter(registro_padron=self.registros[1]).update(mesa=self.destino)
        titular = AsignacionAutoridad(registro_padron=self.registros[0], mesa=self.destino, turno=self.manana, tipo="titular", asignada_por=self.usuario)
        suplente = AsignacionAutoridad(registro_padron=self.registros[1], mesa=self.destino, turno=self.manana, tipo="suplente", asignada_por=self.usuario)
        with self.assertRaisesMessage(ValidationError, "capacidad"):
            reacomodar_titulares(self.eleccion_claustro, [titular, suplente], self.usuario)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa_id, self.destino.pk)
