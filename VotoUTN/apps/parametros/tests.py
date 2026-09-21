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
from apps.partidos.forms import FormularioCargoElectivo
from apps.partidos.models import CargoElectivo, OrganoElectivo


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

    def test_panel_incluye_los_siete_catalogos_y_puestos_a_elegir(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-parametros"))

        self.assertEqual(len(respuesta.context["parametros"]), 8)
        self.assertContains(respuesta, "Plantillas de mensajes")
        self.assertContains(respuesta, "Puestos a elegir")
        self.assertNotContains(respuesta, "Agrupaciones y cargos a elegir")

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
        self.assertEqual(OrganoElectivo.objects.count(), 3)
        self.assertEqual(CargoElectivo.objects.count(), 3)
        self.assertEqual(TipoJustificativo.objects.count(), 0)
        puesto_departamental = CargoElectivo.objects.get(
            organo__nombre="Consejo Departamental",
            nombre="Consejero/a departamental",
        )
        self.assertTrue(puesto_departamental.permite_filtrar_claustros)
        self.assertTrue(puesto_departamental.permite_filtrar_departamentos)
        plantilla = PlantillaNotificacion.objects.get(codigo="padron-definitivo-publicado")
        plantilla.activa = False
        plantilla.save(update_fields=("activa",))
        extra = Sede.objects.create(nombre="Sede personalizada", activa=False)
        ids = {codigo: pk for codigo, pk in PlantillaNotificacion.objects.values_list("codigo", "pk")}

        call_command("cargar_parametros_estandar", stdout=StringIO())

        self.assertEqual(PlantillaNotificacion.objects.count(), 26)
        self.assertEqual(OrganoElectivo.objects.count(), 3)
        self.assertEqual(CargoElectivo.objects.count(), 3)
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


class CatalogosCandidaturasTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="admin_candidaturas", password="clave")
        self.client.login(username="admin_candidaturas", password="clave")

    def test_panel_muestra_un_unico_acceso_a_puestos(self):
        respuesta = self.client.get(reverse("catalogos-candidaturas"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Agrupaciones")
        self.assertContains(respuesta, "Órganos o cuerpos")
        self.assertContains(respuesta, "Puestos a elegir")
        self.assertEqual(len(respuesta.context["catalogos"]), 2)

    def test_se_crean_organo_y_cargo_y_el_estado_se_audita(self):
        respuesta = self.client.post(reverse("crear-parametro", args=("organos-electivos",)), {
            "nombre": "DASUTeN", "descripcion": "Obra social", "activo": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        organo = OrganoElectivo.objects.get(nombre="DASUTeN")
        respuesta = self.client.post(reverse("crear-parametro", args=("puestos-electivos",)), {
            "organo": organo.pk, "nombre": "Representante", "permite_filtrar_claustros": "on",
            "permite_filtrar_departamentos": "on", "descripcion": "", "activo": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        cargo = CargoElectivo.objects.get(organo=organo, nombre="Representante")
        self.client.post(reverse("cambiar-estado-parametro", args=("puestos-electivos", cargo.pk)))
        cargo.refresh_from_db()
        self.assertFalse(cargo.activo)
        self.assertEqual(EventoAuditoria.objects.filter(entidad="partidos.CargoElectivo").count(), 2)

    def test_cargo_unico_por_organo_y_organo_inactivo_no_se_ofrece(self):
        primero = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        segundo = OrganoElectivo.objects.create(nombre="Consejo Superior")
        inactivo = OrganoElectivo.objects.create(nombre="Inactivo", activo=False)
        CargoElectivo.objects.create(organo=primero, nombre="Representante")

        duplicado = FormularioCargoElectivo(data={
            "organo": primero.pk, "nombre": "Representante", "permite_filtrar_claustros": "on", "activo": "on",
        })
        otro_organo = FormularioCargoElectivo(data={
            "organo": segundo.pk, "nombre": "Representante", "permite_filtrar_claustros": "on", "activo": "on",
        })
        formulario_nuevo = FormularioCargoElectivo()

        self.assertFalse(duplicado.is_valid())
        self.assertTrue(otro_organo.is_valid())
        self.assertNotIn(inactivo, formulario_nuevo.fields["organo"].queryset)

    def test_puesto_sin_filtros_es_valido_y_se_aplicara_a_todos(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        formulario = FormularioCargoElectivo(data={
            "organo": organo.pk,
            "nombre": "Representante",
            "activo": "on",
        })

        self.assertTrue(formulario.is_valid())

    def test_listado_permite_buscar_cargos_por_organo(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        CargoElectivo.objects.create(organo=organo, nombre="Representante")

        respuesta = self.client.get(reverse("listar-parametros", args=("puestos-electivos",)), {"q": "Directivo"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Representante")
