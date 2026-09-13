from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from io import StringIO

from apps.auditoria.models import EventoAuditoria
from apps.justificativos.models import TipoJustificativo
from apps.notificaciones.models import PlantillaNotificacion
from apps.parametros.forms import FormularioFechaAdministrativa
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


class ParametrosViewsTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="admin", password="clave")

    def test_gestionar_parametros_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-parametros"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "parametros/gestion.html")

    def test_listar_parametros_usa_ruta_publica_existente(self):
        Sede.objects.create(nombre="Campus")
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("listar-parametros", args=("sedes",)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "parametros/lista.html")

    def test_panel_incluye_los_siete_catalogos(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-parametros"))

        self.assertEqual(len(respuesta.context["parametros"]), 7)
        self.assertContains(respuesta, "Plantillas de mensajes")

    def test_alta_y_cambio_de_estado_quedan_auditados(self):
        self.client.login(username="admin", password="clave")
        self.client.post(reverse("crear-parametro", args=("sedes",)), {"nombre": "Medrano", "activa": "on"})
        sede = Sede.objects.get(nombre="Medrano")
        self.client.post(reverse("cambiar-estado-parametro", args=("sedes", sede.pk)))

        self.assertEqual(EventoAuditoria.objects.filter(entidad="parametros.Sede").count(), 2)
        sede.refresh_from_db()
        self.assertFalse(sede.activa)


class CatalogosEstandarTests(TestCase):
    def test_carga_exacta_es_idempotente_reactiva_y_no_elimina_personalizados(self):
        salida = StringIO()
        call_command("cargar_parametros_estandar", stdout=salida)

        self.assertEqual(Sede.objects.filter(nombre__in=("Medrano", "Campus")).count(), 2)
        self.assertEqual(Claustro.objects.count(), 4)
        self.assertEqual(Turno.objects.count(), 3)
        self.assertEqual(Departamento.objects.count(), 10)
        self.assertEqual(FechaAdministrativa.objects.count(), 6)
        self.assertEqual(PlantillaNotificacion.objects.count(), 26)
        self.assertEqual(TipoJustificativo.objects.count(), 0)
        plantilla = PlantillaNotificacion.objects.get(codigo="padron-definitivo-publicado")
        plantilla.activa = False
        plantilla.save(update_fields=("activa",))
        extra = Sede.objects.create(nombre="Sede personalizada", activa=False)
        ids = {codigo: pk for codigo, pk in PlantillaNotificacion.objects.values_list("codigo", "pk")}

        call_command("cargar_parametros_estandar", stdout=StringIO())

        self.assertEqual(PlantillaNotificacion.objects.count(), 26)
        self.assertEqual(ids, {codigo: pk for codigo, pk in PlantillaNotificacion.objects.values_list("codigo", "pk")})
        plantilla.refresh_from_db()
        self.assertTrue(plantilla.activa)
        self.assertTrue(Sede.objects.filter(pk=extra.pk).exists())


class ValidacionesCatalogosTests(TestCase):
    def test_fecha_por_duracion_exige_cantidad_de_dias(self):
        formulario = FormularioFechaAdministrativa(data={
            "codigo": "periodo", "nombre": "Periodo", "modalidad_sugerida": "duracion",
            "roles_destinatarios": [FechaAdministrativa.RolDestinatario.ELECTOR],
            "alcance_todos_claustros": "on", "criterio_destinatarios": "todos_en_alcance",
            "activa": "on",
        })

        self.assertFalse(formulario.is_valid())
        self.assertIn("duracion_sugerida_dias", formulario.errors)

    def test_plantilla_rechaza_variables_desconocidas(self):
        plantilla = PlantillaNotificacion(
            codigo="invalida", nombre="Inválida", asunto="Hola {dni}", contenido="Texto",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
        )

        with self.assertRaises(ValidationError):
            plantilla.full_clean()
