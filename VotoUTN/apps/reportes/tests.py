from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion
from apps.reportes.services import valor_csv
from apps.usuarios.models import AsignacionRol


class ReportesCSVTests(TestCase):
    def test_valor_csv_sanitiza_formulas(self):
        self.assertEqual(valor_csv("=1+1"), "'=1+1")
        self.assertEqual(valor_csv("+SUM(A1:A2)"), "'+SUM(A1:A2)")
        self.assertEqual(valor_csv("-10"), "'-10")
        self.assertEqual(valor_csv("@cmd"), "'@cmd")
        self.assertEqual(valor_csv("Ana Perez"), "Ana Perez")
        self.assertEqual(valor_csv(None), "")


class ReportesViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            habilitada=False,
        )
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )

    def test_gestionar_reportes_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-reportes", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "elecciones/reportes.html")

    def test_exportar_reporte_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("exportar-reporte", args=(self.eleccion.id, "padron")))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])
