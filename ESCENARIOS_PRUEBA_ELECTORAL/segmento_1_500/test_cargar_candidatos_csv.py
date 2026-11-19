from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.auditoria.models import EventoAuditoria
from apps.elecciones.models import EleccionClaustroDepartamento
from apps.padron.models import Elector, RegistroPadron
from apps.partidos.models import Candidato, CargoElectivo, CupoPuestoClaustro, ImportacionCandidaturas, ListaCandidatos, OrganoElectivo, ParticipacionPartido, PuestoEleccion
from apps.usuarios.models import AsignacionRol
from cargar_candidatos_csv import cargar_candidatos
from crear_listas_para_csv import BASE, ErrorPreparacion, leer_csv, leer_definiciones, preparar_listas
import test_crear_listas_para_csv as casos


class CargaAutomaticaCandidatosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        casos.CrearListasEscenarioTests.setUpTestData.__func__(cls)
        cls.usuario = get_user_model().objects.create_user(username="junta-carga-csv")
        AsignacionRol.objects.create(usuario=cls.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA)
        for definicion in cls.definiciones:
            codigo = definicion["codigo_presentacion"]
            for fila in leer_csv(BASE / definicion["csv_candidatos"]):
                config = cls.configuraciones[(codigo, fila["puesto"], fila["departamento"])]
                alcance = config.eleccion_claustro_departamento
                if alcance is None:
                    alcance = EleccionClaustroDepartamento.objects.filter(eleccion_claustro=config.eleccion_claustro).first()
                    if alcance is None:
                        alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=config.eleccion_claustro)
                elector, _ = Elector.objects.get_or_create(
                    tipo_documento=fila["tipo_documento"], dni=fila["documento"],
                    defaults={"nombre": "Candidato", "apellido": "Prueba", "legajo": "T" + fila["documento"]},
                )
                if not RegistroPadron.objects.filter(eleccion=cls.eleccion, elector=elector).exists():
                    RegistroPadron.objects.create(eleccion=cls.eleccion, elector=elector, eleccion_claustro_departamento=alcance)
        cls.no_docentes = leer_definiciones(claustros=["no_docentes"])

    def cargar(self, definiciones=None, **opciones):
        return cargar_candidatos(self.eleccion.pk, self.no_docentes if definiciones is None else definiciones,
                                 usuario=self.usuario, **opciones)

    def test_previsualizacion_no_conserva_listas_candidatos_importaciones_o_auditoria(self):
        eventos = EventoAuditoria.objects.count()
        resultado = self.cargar()
        self.assertEqual(resultado["candidatos_nuevos"], 28)
        self.assertFalse(Candidato.objects.exists())
        self.assertFalse(ParticipacionPartido.objects.exists())
        self.assertFalse(ImportacionCandidaturas.objects.exists())
        self.assertEqual(EventoAuditoria.objects.count(), eventos)

    def test_carga_catorce_listas_con_460_candidaturas_y_340_personas(self):
        resultado = self.cargar(self.definiciones, aplicar=True)
        self.assertEqual(resultado["candidatos_nuevos"], 460)
        self.assertEqual(ParticipacionPartido.objects.count(), 14)
        self.assertEqual(ListaCandidatos.objects.count(), 50)
        self.assertEqual(Candidato.objects.count(), 460)
        self.assertEqual(Candidato.objects.values("elector_id").distinct().count(), 340)
        dasuten = ParticipacionPartido.objects.filter(codigo_presentacion__startswith="DOC-", codigo_presentacion__contains="DASUTEN")
        self.assertEqual(Candidato.objects.filter(lista__participacion__in=dasuten).count(), 8)
        self.assertFalse(Candidato.objects.filter(lista__participacion__in=dasuten, cargo="Consejero/a directivo/a").exists())
        self.assertTrue(any(lista["advertencias"] for lista in resultado["listas"]))

    def test_segunda_carga_omite_identicos_sin_duplicar_auditoria(self):
        self.cargar(aplicar=True)
        eventos = EventoAuditoria.objects.count()
        resultado = self.cargar(aplicar=True)
        self.assertEqual((resultado["candidatos_nuevos"], resultado["candidatos_identicos_omitidos"]), (0, 28))
        self.assertEqual(Candidato.objects.count(), 28)
        self.assertEqual(ImportacionCandidaturas.objects.count(), 2)
        self.assertEqual(EventoAuditoria.objects.count(), eventos)

    def test_completa_una_lista_parcial_sin_cambiar_candidatos_cargados(self):
        self.cargar(aplicar=True)
        candidato = Candidato.objects.first()
        eliminado_id = candidato.pk
        candidato.delete()
        preservados = set(Candidato.objects.values_list("pk", flat=True))
        resultado = self.cargar(aplicar=True)
        self.assertEqual((resultado["candidatos_nuevos"], resultado["candidatos_identicos_omitidos"]), (1, 27))
        self.assertTrue(preservados.issubset(set(Candidato.objects.values_list("pk", flat=True))))
        self.assertFalse(Candidato.objects.filter(pk=eliminado_id).exists())

    def test_error_en_ultimo_csv_revierte_las_importaciones_previas(self):
        ultima = leer_csv(BASE / self.no_docentes[-1]["csv_candidatos"])[-1]["documento"]
        RegistroPadron.objects.filter(elector__dni=ultima).update(activo=False)
        with self.assertRaisesMessage(ErrorPreparacion, "padrón activo"):
            self.cargar(aplicar=True)
        self.assertFalse(Candidato.objects.exists())
        self.assertFalse(ParticipacionPartido.objects.exists())
        self.assertFalse(ImportacionCandidaturas.objects.exists())

    def test_rechaza_usuario_sin_permiso(self):
        AsignacionRol.objects.filter(usuario=self.usuario).update(activo=False)
        with self.assertRaisesMessage(ErrorPreparacion, "permisos"):
            self.cargar(aplicar=True)

    def test_nunca_quita_una_asociacion_con_candidatos(self):
        self.cargar(aplicar=True)
        modificadas = [{**d, "puestos": [p for p in d["puestos"] if p["puesto"] != "Consejero/a Superior"]}
                       for d in self.no_docentes]
        with self.assertRaisesMessage(ErrorPreparacion, "ya tiene candidatos"):
            self.cargar(modificadas, aplicar=True, ajustar_asociaciones=True)
        self.assertEqual(Candidato.objects.count(), 28)

    def test_candidatura_inactiva_no_se_reactiva_automaticamente(self):
        self.cargar(aplicar=True)
        candidato = Candidato.objects.first()
        candidato.activo = False
        candidato.save(update_fields=["activo"])
        with self.assertRaisesMessage(ErrorPreparacion, "inactivo"):
            self.cargar(aplicar=True)
        candidato.refresh_from_db()
        self.assertFalse(candidato.activo)

    def test_fallo_de_auditoria_revierte_candidatos_y_listas(self):
        preparar_listas(self.eleccion.pk, self.no_docentes, aplicar=True, usuario=self.usuario)
        with patch("apps.auditoria.services.registrar_evento", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.cargar(aplicar=True)
        self.assertFalse(Candidato.objects.exists())
        self.assertFalse(ImportacionCandidaturas.objects.exists())

    def test_rechaza_otro_elector_en_un_lugar_ya_ocupado(self):
        self.cargar(aplicar=True)
        candidato = Candidato.objects.first()
        otro = Candidato.objects.exclude(elector=candidato.elector).first()
        Candidato.objects.filter(pk=candidato.pk).update(elector=otro.elector, dni=otro.dni)
        with self.assertRaisesMessage(ErrorPreparacion, "ocupado por otra candidatura"):
            self.cargar(aplicar=True)
        self.assertEqual(Candidato.objects.count(), 28)

    def test_ajuste_retira_solo_asociaciones_vacias_fuera_de_los_csv(self):
        preparar_listas(self.eleccion.pk, self.no_docentes, aplicar=True, usuario=self.usuario)
        participacion = ParticipacionPartido.objects.first()
        cargo = CargoElectivo.objects.create(
            nombre="Puesto extra de prueba", organo=OrganoElectivo.objects.first(),
        )
        cargo.claustros_habilitados.add(participacion.eleccion_claustro.claustro)
        config = PuestoEleccion.objects.create(puesto=cargo, eleccion_claustro=participacion.eleccion_claustro,
                                              cantidad_titulares=1, cantidad_suplentes=1)
        extra = ListaCandidatos.objects.create(participacion=participacion,
                                              eleccion_claustro=participacion.eleccion_claustro,
                                              puesto_eleccion=config, nombre="Asociación vacía")
        resultado = self.cargar(aplicar=True, ajustar_asociaciones=True)
        self.assertEqual(resultado["asociaciones_vacias_retiradas"], 1)
        self.assertFalse(ListaCandidatos.objects.filter(pk=extra.pk).exists())
        self.assertEqual(ListaCandidatos.objects.count(), 6)
        self.assertEqual(Candidato.objects.count(), 28)

    def test_previsualizar_reinicio_conserva_las_listas_y_candidatos_anteriores(self):
        self.cargar(aplicar=True)
        ids = set(Candidato.objects.values_list("pk", flat=True))
        resultado = self.cargar(self.definiciones, reiniciar_listas=True)
        self.assertEqual(resultado["reinicio"]["candidaturas_eliminadas"], 28)
        self.assertEqual(set(Candidato.objects.values_list("pk", flat=True)), ids)
        self.assertEqual(ParticipacionPartido.objects.count(), 2)

    def test_reinicio_respalda_las_listas_y_carga_todo_de_nuevo(self):
        self.cargar(aplicar=True)
        anteriores = set(ParticipacionPartido.objects.values_list("pk", flat=True))
        resultado = self.cargar(self.definiciones, aplicar=True, reiniciar_listas=True)
        self.assertEqual(resultado["reinicio"], {"candidaturas_eliminadas": 28, "asociaciones_eliminadas": 6, "listas_eliminadas": 2})
        self.assertFalse(ParticipacionPartido.objects.filter(pk__in=anteriores).exists())
        self.assertEqual((ParticipacionPartido.objects.count(), ListaCandidatos.objects.count(), Candidato.objects.count()), (14, 50, 460))
        respaldo = EventoAuditoria.objects.get(accion="reiniciar_listas_candidatos_escenario")
        self.assertEqual(len(respaldo.datos_anteriores["candidaturas"]), 28)

    def test_reinicio_con_error_de_importacion_recupera_las_candidaturas_anteriores(self):
        self.cargar(aplicar=True)
        ids = set(Candidato.objects.values_list("pk", flat=True))
        ultimo = leer_csv(BASE / self.no_docentes[-1]["csv_candidatos"])[-1]["documento"]
        RegistroPadron.objects.filter(elector__dni=ultimo).update(activo=False)
        with self.assertRaises(ErrorPreparacion):
            self.cargar(self.definiciones, aplicar=True, reiniciar_listas=True)
        self.assertEqual(set(Candidato.objects.values_list("pk", flat=True)), ids)
        self.assertEqual(ParticipacionPartido.objects.count(), 2)
        self.assertFalse(EventoAuditoria.objects.filter(accion="reiniciar_listas_candidatos_escenario").exists())

    def test_prepara_catalogo_incompleto_y_carga_los_catorce_csv(self):
        PuestoEleccion.objects.all().delete()
        CupoPuestoClaustro.objects.all().delete()
        CargoElectivo.objects.filter(nombre__in=["Consejero/a Superior", "Consejero/a Ciencias Básicas"]).delete()
        resultado = self.cargar(self.definiciones, aplicar=True, preparar_puestos=True, reiniciar_listas=True)
        self.assertEqual(resultado["candidatos_nuevos"], 460)
        self.assertGreater(resultado["parametros_actualizados"], 0)
        self.assertEqual(Candidato.objects.count(), 460)
        self.assertEqual(ListaCandidatos.objects.count(), 50)
        self.assertEqual(CupoPuestoClaustro.objects.get(puesto__nombre="Consejero/a directivo/a", claustro__nombre="Docentes").cantidad_titulares, 2)
        self.assertEqual(CupoPuestoClaustro.objects.get(puesto__nombre="Consejero/a Superior", claustro__nombre="No docentes").cantidad_suplentes, 5)
        self.assertEqual(CupoPuestoClaustro.objects.get(puesto__nombre="Consejero/a DASUTeN", claustro__nombre="No docentes").cantidad_titulares, 2)

    def test_previsualizar_preparacion_no_conserva_cambios_en_parametros(self):
        cupos_antes = list(CupoPuestoClaustro.objects.order_by("pk").values())
        puestos_antes = list(PuestoEleccion.objects.order_by("pk").values())
        self.cargar(preparar_puestos=True)
        self.assertEqual(list(CupoPuestoClaustro.objects.order_by("pk").values()), cupos_antes)
        self.assertEqual(list(PuestoEleccion.objects.order_by("pk").values()), puestos_antes)

    def test_preparacion_no_reactiva_puestos_inactivos(self):
        CargoElectivo.objects.filter(nombre="Consejero/a Superior").update(activo=False)
        with self.assertRaisesMessage(ErrorPreparacion, "inactivo"):
            self.cargar(preparar_puestos=True, aplicar=True)
        self.assertFalse(Candidato.objects.exists())
