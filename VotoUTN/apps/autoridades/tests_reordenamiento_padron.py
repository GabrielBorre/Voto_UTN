from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from unittest.mock import patch

from apps.autoridades.reordenamiento_padron import (
    ElectorPropuesto, GrupoPadron, MesaPropuesta, calcular_padrones_ordenados,
    previsualizar_padrones,
)


class ReordenamientoPadronTests(SimpleTestCase):
    def test_traslada_registro_adicional_junto_a_su_autoridad(self):
        principal_origen = GrupoPadron("Alumnos", "K", "Campus")
        principal_destino = GrupoPadron("Alumnos", "K", "Medrano")
        adicional_origen = GrupoPadron("Alumnos", "I", "Campus", es_especial=True)
        adicional_destino = GrupoPadron("Alumnos", "I", "Medrano", es_especial=True)
        mesas = [MesaPropuesta(1, principal_origen), MesaPropuesta(2, principal_destino), MesaPropuesta(3, adicional_origen)]
        electores = [ElectorPropuesto("principal", principal_origen), ElectorPropuesto("adicional", adicional_origen)]
        resultado = calcular_padrones_ordenados(
            mesas=mesas, electores=electores, titulares={"principal": 2}, maximo=1,
            destinos_adicionales={"adicional": adicional_destino},
        )
        self.assertEqual(resultado["padrones"][2], ["principal"])
        self.assertEqual(resultado["padrones"][(adicional_destino, 1)], ["adicional"])
        self.assertIn(MesaPropuesta((adicional_destino, 1), adicional_destino), resultado["mesas_nuevas"])

    def test_separacion_entre_mesa_ordinaria_y_especial_del_mismo_alcance(self):
        ordinaria = GrupoPadron("Alumnos", "I", "Campus")
        especial = GrupoPadron("Alumnos", "I", "Campus", es_especial=True)
        mesas = [MesaPropuesta(1, ordinaria), MesaPropuesta(2, especial)]
        electores = [ElectorPropuesto("A", ordinaria), ElectorPropuesto("B", especial)]
        resultado = calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={}, maximo=2)
        self.assertEqual(resultado["padrones"], {1: ["A"], 2: ["B"]})
        with self.assertRaisesMessage(ValidationError, "tipo de su mesa"):
            calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"A": 2}, maximo=2)

    def test_reserva_titular_al_final_y_conserva_orden_del_resto(self):
        grupo = GrupoPadron("Alumnos", "K", "Campus")
        mesas = [MesaPropuesta(1, grupo), MesaPropuesta(2, grupo)]
        electores = [ElectorPropuesto(nombre, grupo) for nombre in "ABCDEFX"]
        resultado = calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"X": 1}, maximo=3)
        self.assertEqual(resultado["padrones"][1], ["A", "B", "X"])
        self.assertEqual(resultado["padrones"][2], ["C", "D", "E"])
        self.assertEqual(resultado["padrones"][(grupo, 3)], ["F"])
        self.assertEqual(resultado["mesas_nuevas"], [MesaPropuesta((grupo, 3), grupo)])

    def test_traslado_entre_sedes_informa_alta_y_baja_de_mesas(self):
        campus = GrupoPadron("Alumnos", "K", "Campus")
        medrano = GrupoPadron("Alumnos", "K", "Medrano")
        mesas = [MesaPropuesta(1, campus), MesaPropuesta(2, medrano)]
        electores = [ElectorPropuesto("A", campus), ElectorPropuesto("X", medrano)]
        resultado = calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"X": 1}, maximo=1)
        self.assertEqual(resultado["padrones"][1], ["X"])
        self.assertEqual(resultado["padrones"][(campus, 2)], ["A"])
        self.assertEqual(resultado["mesas_quitadas"], [2])

    def test_no_reacomoda_otros_grupos_y_rechaza_referencias_invalidas(self):
        k = GrupoPadron("Alumnos", "K", "Campus")
        e = GrupoPadron("Alumnos", "E", "Campus")
        mesas = [MesaPropuesta(1, k), MesaPropuesta(2, e)]
        electores = [ElectorPropuesto("A", k), ElectorPropuesto("B", e)]
        resultado = calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"A": 1}, maximo=2)
        self.assertEqual(resultado["padrones"], {1: ["A"], 2: ["B"]})
        with self.assertRaises(ValidationError):
            calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"A": 9}, maximo=2)
        with self.assertRaisesMessage(ValidationError, "claustro ni de departamento"):
            calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"A": 2}, maximo=2)

    def test_no_supera_capacidad_al_reservar_titulares(self):
        grupo = GrupoPadron("Alumnos", "K", "Campus")
        mesas = [MesaPropuesta(1, grupo)]
        electores = [ElectorPropuesto("A", grupo), ElectorPropuesto("B", grupo)]
        with self.assertRaisesMessage(ValidationError, "superan su capacidad"):
            calcular_padrones_ordenados(mesas=mesas, electores=electores, titulares={"A": 1, "B": 1}, maximo=1)

    def test_conserva_votacion_fija_y_mesa_protegida(self):
        grupo = GrupoPadron("Alumnos", "K", "Campus")
        mesas = [MesaPropuesta(1, grupo), MesaPropuesta(2, grupo), MesaPropuesta(3, grupo)]
        electores = [ElectorPropuesto(n, grupo) for n in "ABCD"]
        resultado = calcular_padrones_ordenados(
            mesas=mesas, electores=electores, titulares={"D": 1}, maximo=3,
            votacion_fija={"A": 2}, mesas_protegidas={3},
        )
        self.assertEqual(resultado["padrones"][1], ["B", "C", "D"])
        self.assertEqual(resultado["padrones"][2], ["A"])
        self.assertEqual(resultado["padrones"][3], [])
        self.assertFalse(resultado["mesas_quitadas"])


class PrevisualizacionPadronTests(TestCase):
    def setUp(self):
        from apps.autoridades import tests as base
        from apps.mesas.models import Mesa
        base.TurnosAutoridadesTests.setUp(self)
        self.otra = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
            generada_automaticamente=True,
        )

    def test_previsualizar_informa_cambios_sin_guardarlos(self):
        from apps.mesas.models import AsignacionMesa, Mesa
        anteriores = list(AsignacionMesa.objects.order_by("pk").values_list("pk", "mesa_id", "autoridad_al_final"))
        ids_mesas = list(Mesa.objects.order_by("pk").values_list("pk", flat=True))
        resultado = previsualizar_padrones(
            self.eleccion_claustro, titulares={self.registros[0].pk: self.otra.pk},
            permitir_cambio_mesa=True, permitir_cambio_sede=False,
        )
        self.assertIn(self.registros[0].pk, resultado["padrones"][self.otra.pk])
        self.assertEqual(list(AsignacionMesa.objects.order_by("pk").values_list("pk", "mesa_id", "autoridad_al_final")), anteriores)
        self.assertEqual(list(Mesa.objects.order_by("pk").values_list("pk", flat=True)), ids_mesas)

    def test_traslado_sin_reordenar_requiere_destino_para_registro_adicional_simulado(self):
        from apps.autoridades.reordenamiento_padron import _planificar_traslado_sin_reordenar
        from apps.elecciones.models import EleccionClaustroDepartamento
        from apps.mesas.models import AsignacionMesa, Mesa
        from apps.padron.models import RegistroPadron
        from apps.parametros.models import Departamento

        principal, adicional = self.registros[:2]
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Industrial", codigo="I-ESP"),
        )
        adicional.eleccion_claustro_departamento = alcance
        adicional.es_principal = False
        adicional.save(update_fields=("eleccion_claustro_departamento", "es_principal"))
        origen_especial = Mesa.objects.create(
            eleccion=self.eleccion, numero=3, sede=self.sede_votacion,
            eleccion_claustro_departamento=alcance, es_especial=True,
        )
        AsignacionMesa.objects.filter(registro_padron=adicional).update(mesa=origen_especial)
        destino_principal = Mesa.objects.create(
            eleccion=self.eleccion, numero=4, sede=self.sede,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
        )
        adicional.elector_id = principal.elector_id  # Simula dos registros de una identidad.
        with patch.object(RegistroPadron.objects, "filter") as buscar:
            buscar.return_value.select_related.return_value.order_by.return_value = [principal, adicional]
            self.assertIsNone(_planificar_traslado_sin_reordenar(principal, destino_principal))
            destino_especial = Mesa.objects.create(
                eleccion=self.eleccion, numero=5, sede=self.sede,
                eleccion_claustro_departamento=alcance, es_especial=True,
            )
            propuesta = _planificar_traslado_sin_reordenar(principal, destino_principal)
        self.assertEqual([(r.pk, m.pk) for r, m in propuesta],
                         [(principal.pk, destino_principal.pk), (adicional.pk, destino_especial.pk)])

    def test_sin_cambio_de_mesa_rechaza_destino_distinto(self):
        with self.assertRaisesMessage(ValidationError, "cambio de mesa no está habilitado"):
            previsualizar_padrones(
                self.eleccion_claustro, titulares={self.registros[0].pk: self.otra.pk},
                permitir_cambio_mesa=False, permitir_cambio_sede=False,
            )

    def test_conserva_restriccion_de_cursada_en_sede_de_origen(self):
        from apps.mesas.models import Mesa
        destino = Mesa.objects.create(
            eleccion=self.eleccion, numero=3, sede=self.sede,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
        )
        registro = self.registros[0]
        registro.sede = self.sede_votacion
        registro.turno_cursada = self.tarde
        registro.save(update_fields=("sede", "turno_cursada"))
        with self.assertRaisesMessage(ValidationError, "cursa en su sede electoral de origen"):
            previsualizar_padrones(
                self.eleccion_claustro, titulares={registro.pk: destino.pk},
                permitir_cambio_mesa=True, permitir_cambio_sede=True,
            )
