from datetime import date, timedelta
from io import StringIO

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.admin_permissions import EleccionCerradaAdminMixin
from apps.elecciones.models import Eleccion, EleccionSede
from apps.mesas.models import AsignacionMesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Sede


class CargaEleccionCerradaDemoTests(TestCase):
    def test_comando_carga_eleccion_cerrada_con_padron_mesa_y_participacion_idempotentemente(self):
        call_command("seed_eleccion_cerrada_demo", stdout=StringIO())
        call_command("seed_eleccion_cerrada_demo", stdout=StringIO())

        eleccion = Eleccion.objects.get(nombre="Eleccion 2024 demo")
        elector = Elector.objects.get(dni="38999222")
        registro_padron = RegistroPadron.objects.get(elector=elector, eleccion=eleccion)

        self.assertEqual(eleccion.fecha_inicio, date(2024, 3, 15))
        self.assertEqual(eleccion.fecha_fin, date(2024, 11, 20))
        self.assertEqual(eleccion.estado, Eleccion.Estado.CERRADA)
        self.assertFalse(eleccion.habilitada)
        self.assertEqual(Eleccion.objects.filter(nombre="Eleccion 2024 demo").count(), 1)
        self.assertEqual(eleccion.elecciones_sede.count(), 1)
        self.assertEqual(eleccion.elecciones_claustro.count(), 1)
        self.assertEqual(
            eleccion.elecciones_claustro.get().fecha_votacion,
            date(2024, 11, 20),
        )
        self.assertEqual(eleccion.mesas.count(), 1)
        self.assertEqual(eleccion.registros_padron.count(), 1)
        self.assertTrue(AsignacionMesa.objects.filter(registro_padron=registro_padron).exists())
        self.assertTrue(RegistroParticipacion.objects.filter(registro_padron=registro_padron).exists())


class EleccionCerradaAdminTests(TestCase):
    def setUp(self):
        fecha = timezone.localdate()
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion cerrada admin de prueba",
            fecha_inicio=fecha - timedelta(days=2),
            fecha_fin=fecha - timedelta(days=1),
            estado=Eleccion.Estado.CERRADA,
            habilitada=False,
        )
        self.sede = Sede.objects.create(nombre="Sede cerrada admin de prueba")
        self.eleccion_sede = EleccionSede.objects.create(
            eleccion=self.eleccion,
            sede=self.sede,
        )
        self.usuario = get_user_model().objects.create_superuser(
            username="superusuario-eleccion-cerrada",
            email="superusuario@example.invalid",
        )
        self.solicitud = RequestFactory().get("/")
        self.solicitud.user = self.usuario

    def test_admin_no_permite_modificar_eleccion_cerrada_ni_sus_relaciones(self):
        admin_eleccion = EleccionCerradaAdminMixin(Eleccion, AdminSite())
        admin_sede = EleccionCerradaAdminMixin(EleccionSede, AdminSite())

        self.assertFalse(admin_eleccion.has_change_permission(self.solicitud, self.eleccion))
        self.assertFalse(admin_sede.has_change_permission(self.solicitud, self.eleccion_sede))
        with self.assertRaises(PermissionDenied):
            admin_sede.save_model(self.solicitud, self.eleccion_sede, None, True)
