from django.test import SimpleTestCase

from apps.padron.models import AsignacionSedePadron, RegistroPadron
from apps.padron.services import _propagar_sede_principal


class SedesCompartidasTests(SimpleTestCase):
    def setUp(self):
        self.principal = RegistroPadron(pk=1, elector_id=10, es_principal=True)
        self.adicional = RegistroPadron(pk=2, elector_id=10, es_principal=False)

    def test_adicional_hereda_sede_y_regla_del_principal(self):
        asignacion = AsignacionSedePadron(
            registro_padron=self.principal, sede_id=7, regla_aplicada_id=3,
            estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        nuevas, pendientes = _propagar_sede_principal([self.adicional, self.principal], [asignacion], {})
        self.assertEqual(len(nuevas), 1)
        self.assertEqual((nuevas[0].registro_padron_id, nuevas[0].sede_id, nuevas[0].regla_aplicada_id), (2, 7, 3))
        self.assertEqual(nuevas[0].estado, AsignacionSedePadron.Estado.ASIGNADA)
        self.assertEqual(pendientes, 0)

    def test_adicional_hereda_estado_pendiente_de_principal_protegido(self):
        principal = AsignacionSedePadron(registro_padron=self.principal, estado=AsignacionSedePadron.Estado.PENDIENTE)
        nuevas, pendientes = _propagar_sede_principal([self.principal, self.adicional], [], {1: principal})
        self.assertIsNone(nuevas[0].sede_id)
        self.assertEqual(nuevas[0].estado, AsignacionSedePadron.Estado.PENDIENTE)
        self.assertEqual(pendientes, 1)

    def test_rechaza_adicional_sin_principal_activo(self):
        with self.assertRaisesMessage(ValueError, "registro principal activo"):
            _propagar_sede_principal([self.adicional], [], {})

    def test_rechaza_sede_protegida_que_contradice_la_principal(self):
        principal = AsignacionSedePadron(
            registro_padron=self.principal, sede_id=7, estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        protegida = AsignacionSedePadron(
            registro_padron=self.adicional, sede_id=8, estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        with self.assertRaisesMessage(ValueError, "sede protegida"):
            _propagar_sede_principal([self.principal, self.adicional], [principal], {2: protegida})

    def test_conserva_sede_protegida_coincidente(self):
        principal = AsignacionSedePadron(
            registro_padron=self.principal, sede_id=7, estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        protegida = AsignacionSedePadron(
            registro_padron=self.adicional, sede_id=7, estado=AsignacionSedePadron.Estado.ASIGNADA,
        )
        nuevas, pendientes = _propagar_sede_principal([self.principal, self.adicional], [principal], {2: protegida})
        self.assertEqual(nuevas, [])
        self.assertEqual(pendientes, 0)

    def test_rechaza_dos_registros_principales(self):
        otro = RegistroPadron(pk=3, elector_id=10, es_principal=True)
        with self.assertRaisesMessage(ValueError, "más de un registro principal"):
            _propagar_sede_principal([self.principal, otro], [], {})
