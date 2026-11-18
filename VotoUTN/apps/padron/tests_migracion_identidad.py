from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigracionIdentidadMultidepartamentalTests(TransactionTestCase):
    """Actualiza una base que ya tiene principales y adicionales, sin campos DNI/legajo."""

    origen = [
        ("padron", "0015_registros_por_departamento"),
        ("elecciones", "0036_alcance_solo_puesto_electivo"),
    ]

    def setUp(self):
        super().setUp()
        ejecutor = MigrationExecutor(connection)
        self.destinos = ejecutor.loader.graph.leaf_nodes()
        ejecutor.migrate(self.origen)
        anteriores = ejecutor.loader.project_state(self.origen).apps
        Eleccion = anteriores.get_model("elecciones", "Eleccion")
        Claustro = anteriores.get_model("parametros", "Claustro")
        Departamento = anteriores.get_model("parametros", "Departamento")
        EleccionClaustro = anteriores.get_model("elecciones", "EleccionClaustro")
        Alcance = anteriores.get_model("elecciones", "EleccionClaustroDepartamento")
        Elector = anteriores.get_model("padron", "Elector")
        Registro = anteriores.get_model("padron", "RegistroPadron")
        hoy = timezone.localdate()
        eleccion = Eleccion.objects.create(nombre="Migración identidad", fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=1))
        claustro = EleccionClaustro.objects.create(
            eleccion=eleccion, claustro=Claustro.objects.create(nombre="Claustro migración"),
        )
        alcances = [Alcance.objects.create(
            eleccion_claustro=claustro,
            departamento=Departamento.objects.create(codigo=codigo, nombre=f"Departamento {codigo}"),
        ) for codigo in ("M1", "M2")]
        elector = Elector.objects.create(dni="40111111", legajo="L100", nombre="Persona", apellido="Prueba")
        momento = timezone.now()
        principal = Registro.objects.create(
            elector=elector, eleccion=eleccion, eleccion_claustro_departamento=alcances[0],
            es_principal=True, identificador_qr="PRINC001", qr_generado_en=momento, numero_mesa_qr=7,
        )
        adicional = Registro.objects.create(
            elector=elector, eleccion=eleccion, eleccion_claustro_departamento=alcances[1],
            es_principal=False, identificador_qr="ADIC0001", qr_generado_en=momento, numero_mesa_qr=8,
        )
        self.eleccion_id = eleccion.pk
        self.elector_id = elector.pk
        self.alcance_id = alcances[0].pk
        self.registros = list(Registro.objects.filter(pk__in=(principal.pk, adicional.pk)).order_by("pk").values())

    def tearDown(self):
        try:
            MigrationExecutor(connection).migrate(self.destinos)
        finally:
            super().tearDown()

    def actualizar(self):
        ejecutor = MigrationExecutor(connection)
        ejecutor.migrate(self.destinos)
        return ejecutor.loader.project_state(self.destinos).apps

    def test_preserva_registros_y_qr_al_copiar_identificadores(self):
        posteriores = self.actualizar()
        Registro = posteriores.get_model("padron", "RegistroPadron")
        registros = list(Registro.objects.filter(eleccion_id=self.eleccion_id).order_by("pk").values())
        self.assertEqual(len(registros), 2)
        for anterior, actual in zip(self.registros, registros, strict=True):
            self.assertEqual(actual.pop("dni"), "40111111")
            self.assertEqual(actual.pop("legajo"), "L100")
            self.assertEqual(actual, anterior)

    def test_dni_admite_adicional_y_rechaza_otro_principal(self):
        posteriores = self.actualizar()
        Elector = posteriores.get_model("padron", "Elector")
        Registro = posteriores.get_model("padron", "RegistroPadron")
        otro = Elector.objects.create(dni="40111111", legajo="L200", nombre="Otra persona")
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                Registro.objects.create(
                    elector_id=otro.pk, eleccion_id=self.eleccion_id,
                    eleccion_claustro_departamento_id=self.alcance_id, es_principal=True,
                    dni="40111111", legajo="L200", identificador_qr="DUPL0001",
                )
        self.assertEqual(error.exception.__cause__.diag.constraint_name, "dni_unico_por_eleccion")
        self.assertEqual(Registro.objects.filter(eleccion_id=self.eleccion_id).count(), 2)

    def test_legajo_admite_adicional_y_rechaza_otro_principal(self):
        posteriores = self.actualizar()
        Elector = posteriores.get_model("padron", "Elector")
        Registro = posteriores.get_model("padron", "RegistroPadron")
        otro = Elector.objects.create(dni="40222222", legajo="L100", nombre="Otra persona")
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                Registro.objects.create(
                    elector_id=otro.pk, eleccion_id=self.eleccion_id,
                    eleccion_claustro_departamento_id=self.alcance_id, es_principal=True,
                    dni="40222222", legajo="L100", identificador_qr="DUPL0002",
                )
        self.assertEqual(error.exception.__cause__.diag.constraint_name, "legajo_unico_por_eleccion")
        self.assertEqual(Registro.objects.filter(eleccion_id=self.eleccion_id).count(), 2)
