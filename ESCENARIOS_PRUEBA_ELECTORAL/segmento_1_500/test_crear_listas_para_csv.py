"""Pruebas con la base PostgreSQL de pruebas de Django; nunca usan la base habitual."""

from datetime import date
from unittest.mock import patch

from django.test import TestCase

from apps.auditoria.models import EventoAuditoria
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.parametros.models import Claustro, Departamento
from apps.partidos.models import Candidato, CargoElectivo, ListaCandidatos, OrganoElectivo, ParticipacionPartido, PuestoEleccion
from crear_listas_para_csv import BASE, ErrorPreparacion, leer_definiciones, preparar_listas


class CrearListasEscenarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.definiciones = leer_definiciones()
        cls.eleccion = Eleccion.objects.create(
            nombre="Escenario listas CSV", fecha_inicio=date(2026, 11, 18), fecha_fin=date(2026, 11, 19),
        )
        cls.configuraciones = {}
        for definicion in cls.definiciones:
            claustro, _ = Claustro.objects.get_or_create(nombre=definicion["claustro"])
            alcance, _ = EleccionClaustro.objects.get_or_create(eleccion=cls.eleccion, claustro=claustro)
            for requisito in definicion["puestos"]:
                organo, _ = OrganoElectivo.objects.get_or_create(nombre=requisito["organo"])
                cargo, _ = CargoElectivo.objects.get_or_create(
                    organo=organo, nombre=requisito["puesto"],
                    defaults={"permite_filtrar_departamentos": bool(requisito["departamento"])},
                )
                cargo.claustros_habilitados.add(claustro)
                departamental = None
                if requisito["departamento"]:
                    depto, _ = Departamento.objects.get_or_create(
                        nombre=requisito["departamento"], defaults={"codigo": f"T{Departamento.objects.count() + 1:02}"},
                    )
                    departamental, _ = EleccionClaustroDepartamento.objects.get_or_create(
                        eleccion_claustro=alcance, departamento=depto,
                    )
                config, _ = PuestoEleccion.objects.get_or_create(
                    eleccion_claustro=alcance, eleccion_claustro_departamento=departamental, puesto=cargo,
                    defaults={"cantidad_titulares": requisito["titulares"], "cantidad_suplentes": requisito["suplentes"]},
                )
                cls.configuraciones[(definicion["codigo_presentacion"], requisito["puesto"], requisito["departamento"])] = config

    def test_lee_catorce_listas_y_cincuenta_asociaciones(self):
        self.assertEqual(len(self.definiciones), 14)
        self.assertEqual(sum(len(d["puestos"]) for d in self.definiciones), 50)
        for definicion in self.definiciones:
            self.assertTrue((BASE / definicion["csv_candidatos"]).is_file())

    def test_previsualizar_no_escribe(self):
        antes = EventoAuditoria.objects.count()
        resultado = preparar_listas(self.eleccion.pk, self.definiciones)
        self.assertEqual(resultado["listas_nuevas"], 14)
        self.assertEqual(resultado["asociaciones_nuevas"], 50)
        self.assertFalse(ParticipacionPartido.objects.exists())
        self.assertFalse(ListaCandidatos.objects.exists())
        self.assertEqual(EventoAuditoria.objects.count(), antes)

    def test_crea_listas_y_puestos_sin_candidatos(self):
        resultado = preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)
        self.assertTrue(resultado["aplicado"])
        self.assertEqual(ParticipacionPartido.objects.count(), 14)
        self.assertEqual(ListaCandidatos.objects.count(), 50)
        self.assertEqual(Candidato.objects.count(), 0)
        self.assertEqual(EventoAuditoria.objects.filter(accion="crear_presentacion_desde_escenario").count(), 14)
        self.assertEqual(EventoAuditoria.objects.filter(accion="vincular_puesto_a_presentacion").count(), 50)
        for lista in ListaCandidatos.objects.select_related("puesto_eleccion"):
            self.assertEqual(lista.eleccion_claustro_id, lista.puesto_eleccion.eleccion_claustro_id)
            self.assertEqual(lista.eleccion_claustro_departamento_id, lista.puesto_eleccion.eleccion_claustro_departamento_id)

    def test_segunda_ejecucion_no_duplica_ni_reaudita(self):
        preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)
        eventos = EventoAuditoria.objects.count()
        resultado = preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)
        self.assertEqual((resultado["listas_nuevas"], resultado["asociaciones_nuevas"]), (0, 0))
        self.assertEqual(ParticipacionPartido.objects.count(), 14)
        self.assertEqual(ListaCandidatos.objects.count(), 50)
        self.assertEqual(EventoAuditoria.objects.count(), eventos)

    def test_reutiliza_presentacion_manual_y_conserva_apoderado(self):
        definicion = self.definiciones[0]
        alcance = EleccionClaustro.objects.get(eleccion=self.eleccion, claustro__nombre=definicion["claustro"])
        manual = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, eleccion_claustro=alcance, codigo_presentacion="MAN-EXISTENTE",
            numero_lista=definicion["numero_lista"], nombre_lista=definicion["nombre_lista"],
            apoderado_nombre="Apoderado registrado", apoderado_email="registrado@example.org",
        )
        resultado = preparar_listas(self.eleccion.pk, [definicion], aplicar=True)
        manual.refresh_from_db()
        self.assertEqual(resultado["listas_nuevas"], 0)
        self.assertEqual(manual.codigo_presentacion, "MAN-EXISTENTE")
        self.assertEqual(manual.apoderado_nombre, "Apoderado registrado")
        self.assertEqual(ParticipacionPartido.objects.count(), 1)

    def test_puesto_faltante_no_deja_carga_parcial(self):
        config = next(iter(self.configuraciones.values()))
        config.activo = False
        config.save(update_fields=["activo"])
        with self.assertRaisesMessage(ErrorPreparacion, "falta un puesto"):
            preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)
        self.assertFalse(ParticipacionPartido.objects.exists())
        self.assertFalse(ListaCandidatos.objects.exists())

    def test_fallo_de_auditoria_revierte_toda_la_operacion(self):
        with patch("apps.auditoria.services.registrar_evento", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)
        self.assertFalse(ParticipacionPartido.objects.exists())
        self.assertFalse(ListaCandidatos.objects.exists())

    def test_codigo_ajeno_o_presentacion_inactiva_no_se_sobrescribe(self):
        definicion = self.definiciones[0]
        alcance = EleccionClaustro.objects.get(eleccion=self.eleccion, claustro__nombre=definicion["claustro"])
        existente = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, eleccion_claustro=alcance, codigo_presentacion=definicion["codigo_presentacion"],
            numero_lista="999", nombre_lista="Lista distinta",
        )
        with self.assertRaisesMessage(ErrorPreparacion, "otra identidad"):
            preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)
        existente.refresh_from_db()
        self.assertEqual(existente.numero_lista, "999")
        self.assertEqual(ParticipacionPartido.objects.count(), 1)
        self.assertFalse(ListaCandidatos.objects.exists())

    def test_rechaza_eleccion_fuera_de_preparacion(self):
        for estado in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO, Eleccion.Estado.FINALIZADA):
            self.eleccion.estado = estado
            self.eleccion.save(update_fields=["estado"])
            with self.assertRaisesMessage(ErrorPreparacion, "En preparación"):
                preparar_listas(self.eleccion.pk, self.definiciones, aplicar=True)

    def test_rechaza_cupo_directivo_docente_incompatible_con_minimo(self):
        docentes = leer_definiciones(claustros=["docentes"])
        config = self.configuraciones[(docentes[0]["codigo_presentacion"], "Consejero/a directivo/a", "")]
        config.cantidad_titulares = config.cantidad_suplentes = 5
        config.save(update_fields=["cantidad_titulares", "cantidad_suplentes"])
        with self.assertRaisesMessage(ErrorPreparacion, "2+2"):
            preparar_listas(self.eleccion.pk, docentes, aplicar=True)
        self.assertFalse(ParticipacionPartido.objects.exists())

    def test_asociacion_faltante_se_agrega_sin_recrear_lista(self):
        definicion = self.definiciones[0]
        preparar_listas(self.eleccion.pk, [definicion], aplicar=True)
        ListaCandidatos.objects.first().delete()
        resultado = preparar_listas(self.eleccion.pk, [definicion], aplicar=True)
        self.assertEqual((resultado["listas_nuevas"], resultado["asociaciones_nuevas"]), (0, 1))

    def test_filtra_un_claustro_y_no_crea_los_demas(self):
        definiciones = leer_definiciones(claustros=["no_docentes"])
        resultado = preparar_listas(self.eleccion.pk, definiciones, aplicar=True)
        self.assertEqual((resultado["listas_nuevas"], resultado["asociaciones_nuevas"]), (2, 4))
        self.assertEqual(set(ParticipacionPartido.objects.values_list("eleccion_claustro__claustro__nombre", flat=True)), {"No docentes"})
