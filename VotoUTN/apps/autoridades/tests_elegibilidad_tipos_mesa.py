from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from apps.autoridades import tests as casos_base
from apps.autoridades.distribucion import _puede_trabajar, _puede_trabajar_nomina, distribuir
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades
from apps.autoridades.nomina import confirmar_nomina, previsualizar_nomina
from apps.autoridades.reordenamiento_padron import (
    aplicar_padrones, aplicar_traslados_sin_reordenar, previsualizar_padrones,
)
from apps.elecciones.models import EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron
from apps.parametros.models import Departamento


class ElegibilidadTiposMesaTests(TestCase):
    def setUp(self):
        casos_base.TurnosAutoridadesTests.setUp(self)
        self.alcance = self.mesa.eleccion_claustro_departamento
        self.opciones = SimpleNamespace(
            modo="nomina", reacomodar_titulares=True,
            permitir_mesa_distinta=False, permitir_cambio_sede=True,
        )

    def crear_mesa(self, alcance=None, *, especial=False, otra_sede=False):
        return Mesa.objects.create(
            eleccion=self.eleccion, numero=Mesa.objects.count() + 1,
            eleccion_claustro_departamento=alcance or self.alcance,
            sede=self.sede if otra_sede else self.sede_votacion,
            generada_automaticamente=True, es_especial=especial,
        )

    def crear_adicional(self, codigo="I"):
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre=f"Departamento {codigo}", codigo=codigo),
        )
        for sede in (self.sede, self.sede_votacion):
            EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=alcance, sede=sede)
        adicional = RegistroPadron.objects.create(
            elector=self.registros[0].elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=alcance, es_principal=False,
        )
        AsignacionMesa.objects.create(registro_padron=adicional, mesa=self.crear_mesa(alcance, especial=True))
        AsignacionSedePadron.objects.create(
            registro_padron=adicional, sede=self.sede_votacion, estado="asignada",
        )
        return adicional

    def test_rechaza_cruces_de_tipo_en_ambos_sentidos_y_sedes(self):
        principal = self.registros[0]
        adicional = self.crear_adicional()
        for otra_sede in (False, True):
            for registro, especial in ((principal, True), (adicional, False)):
                with self.subTest(otra_sede=otra_sede, principal=registro.es_principal):
                    destino = self.crear_mesa(registro.eleccion_claustro_departamento,
                                             especial=especial, otra_sede=otra_sede)
                    self.assertFalse(_puede_trabajar_nomina(registro, destino, self.manana, self.opciones))

    def test_destino_laboral_fijado_no_permite_omitir_el_tipo(self):
        registro = self.registros[0]
        destino = self.crear_mesa(especial=True)
        CandidaturaAutoridad.objects.create(
            registro_padron=registro, cargada_por=self.usuario,
            mesa_traslado=destino, turno_traslado=self.manana,
        )
        self.assertFalse(_puede_trabajar_nomina(registro, destino, self.manana, self.opciones))
        self.assertFalse(_puede_trabajar(registro, destino, self.manana, "nomina"))

    def test_mesa_distinta_sin_reordenar_tambien_exige_tipo_compatible(self):
        self.opciones.reacomodar_titulares = False
        self.opciones.permitir_mesa_distinta = True
        self.opciones.permitir_cambio_sede = False
        adicional = self.crear_adicional()
        for registro in (self.registros[0], adicional):
            with self.subTest(principal=registro.es_principal):
                compatible = self.crear_mesa(registro.eleccion_claustro_departamento,
                                             especial=not registro.es_principal)
                incompatible = self.crear_mesa(registro.eleccion_claustro_departamento,
                                               especial=registro.es_principal)
                self.assertTrue(_puede_trabajar_nomina(registro, compatible, self.manana, self.opciones))
                self.assertFalse(_puede_trabajar_nomina(registro, incompatible, self.manana, self.opciones))

    def test_seleccion_manual_fijada_no_habilita_un_cruce_de_tipo(self):
        registro = self.registros[0]
        destino = self.crear_mesa(especial=True)
        CandidaturaAutoridad.objects.create(
            registro_padron=registro, cargada_por=self.usuario,
            mesa_manual=destino, turno_manual=self.manana, tipo_manual="titular",
        )
        self.assertFalse(_puede_trabajar(registro, destino, self.manana, "manual"))

    def test_vacantes_de_tipo_incompatible_no_rompen_las_dos_alternativas(self):
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, minimo_titulares_por_mesa=1)
        for cambio_sede in (False, True):
            with self.subTest(cambio_sede=cambio_sede), transaction.atomic():
                especial = self.crear_mesa(especial=True, otra_sede=cambio_sede)
                otro_alcance = EleccionClaustroDepartamento.objects.create(
                    eleccion_claustro=self.eleccion_claustro,
                    departamento=Departamento.objects.create(nombre="Otro principal", codigo="OT"),
                )
                EleccionClaustroDepartamentoSede.objects.create(
                    eleccion_claustro_departamento=otro_alcance, sede=especial.sede,
                )
                persona = Elector.objects.create(dni="49999999", legajo="NO-NOMINA", nombre="Persona fuera de la nomina")
                for alcance, principal, mesa in (
                    (otro_alcance, True, self.crear_mesa(otro_alcance, otra_sede=cambio_sede)),
                    (self.alcance, False, especial),
                ):
                    registro = RegistroPadron.objects.create(
                        elector=persona, eleccion=self.eleccion,
                        eleccion_claustro_departamento=alcance, es_principal=principal,
                    )
                    AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
                    AsignacionSedePadron.objects.create(registro_padron=registro, sede=especial.sede, estado="asignada")
                datos = {"registros": [registro.pk for registro in self.registros[:2]],
                         "mesa": True, "votar_mesa": False, "sede": cambio_sede}

                propuesta = previsualizar_nomina(self.eleccion_claustro, self.usuario, datos)
                codigo = "sede_reacomodo" if cambio_sede else "cambio_mesa"
                alternativa = next(opcion for opcion in propuesta["alternativas"] if opcion["codigo"] == codigo)

                self.assertNotIn("error", alternativa)
                self.assertEqual(alternativa["titulares"], 1)
                self.assertEqual(alternativa["sin_asignar"], 1)
                self.assertGreater(alternativa["titulares_faltantes"], 0)
                confirmar_nomina(self.eleccion_claustro, self.usuario, propuesta, alternativa=codigo)
                asignacion = AsignacionAutoridad.objects.get()
                self.assertFalse(asignacion.mesa.es_especial)
                self.assertTrue(asignacion.registro_padron.es_principal)
                transaction.set_rollback(True)

    def test_asignacion_incompatible_conservada_no_se_reintroduce_en_los_elegibles(self):
        registro = self.registros[0]
        destino = self.crear_mesa(especial=True)
        configuracion = ConfiguracionAutoridades.objects.create(
            eleccion_claustro=self.eleccion_claustro, modo="nomina", permitir_mesa_distinta=True,
        )
        candidatura = CandidaturaAutoridad.objects.create(registro_padron=registro, cargada_por=self.usuario)
        AsignacionAutoridad.objects.create(
            registro_padron=registro, mesa=destino, turno=self.manana,
            candidatura=candidatura, asignada_por=self.usuario,
        )
        with self.assertRaisesMessage(ValidationError, "conservar todas las asignaciones"):
            distribuir(self.eleccion_claustro, self.usuario)
        configuracion.refresh_from_db()
        self.assertTrue(configuracion.permitir_mesa_distinta)
        self.assertEqual(AsignacionAutoridad.objects.get().mesa_id, destino.pk)

    def preparar_traslado_conjunto(self):
        registros = [self.registros[0], self.crear_adicional("I"), self.crear_adicional("O")]
        destinos = {registro.pk: self.crear_mesa(
            registro.eleccion_claustro_departamento, especial=not registro.es_principal, otra_sede=True,
        ) for registro in registros}
        return registros, destinos

    def test_autoridad_principal_o_especial_traslada_todos_sus_registros_sin_cambiar_tipo(self):
        for como_especial in (False, True):
            with self.subTest(como_especial=como_especial), transaction.atomic():
                registros, destinos = self.preparar_traslado_conjunto()
                autoridad = registros[1] if como_especial else registros[0]
                origen = autoridad.asignacion_mesa.mesa
                codigos = {registro.pk: registro.identificador_qr for registro in registros}
                cursada = {registro.pk: registro.sede_id for registro in registros}
                AsignacionAutoridad.objects.create(
                    registro_padron=autoridad, mesa=destinos[autoridad.pk], turno=self.manana,
                    asignada_por=self.usuario, mesa_votacion_original=origen,
                )
                titulares = {autoridad.pk: destinos[autoridad.pk].pk}

                propuesta = previsualizar_padrones(
                    self.eleccion_claustro, titulares=titulares,
                    permitir_cambio_mesa=True, permitir_cambio_sede=True,
                )
                aplicar_padrones(self.eleccion_claustro, propuesta, titulares=titulares)

                for registro in registros:
                    registro.refresh_from_db()
                    fila = AsignacionMesa.objects.get(registro_padron=registro)
                    self.assertEqual(fila.mesa.sede_id, self.sede.pk)
                    self.assertEqual(fila.mesa.es_especial, not registro.es_principal)
                    self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede_id, self.sede.pk)
                    self.assertEqual(registro.identificador_qr, codigos[registro.pk])
                    self.assertEqual(registro.sede_id, cursada[registro.pk])
                self.assertEqual(AsignacionAutoridad.objects.count(), 1)
                transaction.set_rollback(True)

    def test_traslado_sin_reordenar_tambien_mueve_todos_los_registros(self):
        for como_especial in (False, True):
            with self.subTest(como_especial=como_especial), transaction.atomic():
                registros, destinos = self.preparar_traslado_conjunto()
                autoridad = registros[1] if como_especial else registros[0]
                asignacion = AsignacionAutoridad.objects.create(
                    registro_padron=autoridad, mesa=destinos[autoridad.pk], turno=self.manana,
                    asignada_por=self.usuario,
                )

                aplicar_traslados_sin_reordenar([asignacion])

                for registro in registros:
                    fila = AsignacionMesa.objects.get(registro_padron=registro)
                    self.assertEqual(fila.mesa.sede_id, self.sede.pk)
                    self.assertEqual(fila.mesa.es_especial, not registro.es_principal)
                    self.assertEqual(AsignacionSedePadron.objects.get(registro_padron=registro).sede_id, self.sede.pk)
                self.assertEqual(AsignacionAutoridad.objects.count(), 1)
                transaction.set_rollback(True)
