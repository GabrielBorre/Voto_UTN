import importlib

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.padron.models import Elector, ErrorImportacionPadron, ImportacionPadron, RegistroPadron
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


class PropiedadModelosTests(SimpleTestCase):
    def test_modelos_pertenecen_a_su_app_y_conservan_las_tablas(self):
        contratos = (
            (Sede, "parametros", "elecciones_sede"),
            (Claustro, "parametros", "elecciones_claustro"),
            (Turno, "parametros", "elecciones_turno"),
            (Departamento, "parametros", "elecciones_departamento"),
            (FechaAdministrativa, "parametros", "elecciones_fechaadministrativa"),
            (Elector, "padron", "elecciones_elector"),
            (RegistroPadron, "padron", "elecciones_registropadron"),
            (ImportacionPadron, "padron", "elecciones_importacionpadron"),
            (ErrorImportacionPadron, "padron", "elecciones_errorimportacionpadron"),
            (Mesa, "mesas", "elecciones_mesa"),
            (AsignacionMesa, "mesas", "elecciones_asignacionmesa"),
            (CandidaturaAutoridad, "autoridades", "elecciones_candidaturaautoridad"),
            (AsignacionAutoridad, "autoridades", "elecciones_asignacionautoridad"),
            (PreferenciaAutoridad, "autoridades", "elecciones_preferenciaautoridad"),
            (TipoJustificativo, "justificativos", "elecciones_tipojustificativo"),
            (JustificativoAusencia, "justificativos", "elecciones_justificativoausencia"),
            (PlantillaNotificacion, "notificaciones", "elecciones_plantillanotificacion"),
            (EnvioNotificacion, "notificaciones", "elecciones_envionotificacion"),
        )

        for modelo, app_label, tabla in contratos:
            with self.subTest(modelo=modelo.__name__):
                self.assertEqual(modelo._meta.app_label, app_label)
                self.assertEqual(modelo._meta.db_table, tabla)


class MigracionContentTypesTests(TestCase):
    def test_actualiza_app_label_y_preserva_permisos(self):
        ContentType.objects.filter(app_label="mesas", model="mesa").delete()
        content_type = ContentType.objects.create(app_label="elecciones", model="mesa")
        permiso = Permission.objects.create(
            content_type=content_type,
            codename="consultar_mesa_migrada",
            name="Puede consultar la mesa migrada",
        )
        migracion = importlib.import_module(
            "apps.elecciones.migrations.0020_delete_elector_delete_envionotificacion_and_more",
        )

        migracion.actualizar_content_types(importlib.import_module("django.apps").apps, None)

        content_type.refresh_from_db()
        permiso.refresh_from_db()
        self.assertEqual(content_type.app_label, "mesas")
        self.assertEqual(permiso.content_type_id, content_type.id)
