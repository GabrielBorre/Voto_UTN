from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.auditoria.models import EventoAuditoria
from apps.notificaciones.models import PlantillaNotificacion
from apps.parametros.models import FechaAdministrativa


class PlantillaDesdeFechaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="editor", password="prueba")
        self.client.force_login(self.usuario)
        self.url = reverse("crear-plantilla-calendario")
        self.datos = {
            "nueva-nombre": "Aviso personalizado",
            "nueva-asunto": "Aviso de {nombre_eleccion}",
            "nueva-contenido": "Hola {nombre_destinatario}",
            "nueva-roles_destinatarios": ["elector"],
        }

    def test_crea_audita_y_permite_seleccionar_en_fecha(self):
        respuesta = self.client.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 201)
        plantilla = PlantillaNotificacion.objects.get(pk=respuesta.json()["plantilla"]["id"])
        self.assertEqual(plantilla.categoria, "calendario")
        self.assertFalse(plantilla.permite_envio_manual)
        self.assertTrue(plantilla.activa)
        self.assertTrue(EventoAuditoria.objects.filter(entidad=plantilla._meta.label, entidad_id=plantilla.pk).exists())
        respuesta = self.client.post(reverse("crear-parametro", args=("fechas-administrativas",)), {
            "nombre": "Fecha", "estado_eleccion": "publicada",
            "envia_mensaje": "on", "plantilla_mensaje": plantilla.pk,
            "roles_destinatarios": ["elector"], "alcance_todos_claustros": "on",
            "criterio_destinatarios": "todos_en_alcance", "activa": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(FechaAdministrativa.objects.get().plantilla_mensaje, plantilla)

    def test_rechaza_variables_invalidas_y_duplicados_sin_guardar(self):
        self.datos["nueva-contenido"] = "Hola {variable_invalida}"
        respuesta = self.client.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("contenido", respuesta.json()["errores"])
        self.assertFalse(PlantillaNotificacion.objects.exists())
        self.datos["nueva-contenido"] = "Hola"
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 201)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 400)
        self.assertEqual(PlantillaNotificacion.objects.count(), 1)

    def test_exige_permiso_y_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        usuario = get_user_model().objects.create_user(username="sin-permiso")
        self.client.force_login(usuario)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 403)
        self.assertFalse(PlantillaNotificacion.objects.exists())

    def test_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(self.url, self.datos).status_code, 403)
        self.assertFalse(PlantillaNotificacion.objects.exists())

    def test_error_de_fecha_preserva_datos_y_editor(self):
        respuesta = self.client.post(reverse("crear-parametro", args=("fechas-administrativas",)), {
            "nombre": "Conservar este borrador", "envia_mensaje": "on",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "parametros/fecha_formulario.html")
        self.assertContains(respuesta, "Conservar este borrador")
        self.assertContains(respuesta, 'id="crear-plantilla-dialogo"')
        self.assertIn("plantilla_mensaje", respuesta.context["formulario"].errors)
        self.assertFalse(FechaAdministrativa.objects.exists())

    def test_catalogo_crea_sin_codigo_con_editor_compartido(self):
        url = reverse("crear-parametro", args=("plantillas-mensajes",))
        respuesta = self.client.get(url)
        self.assertTemplateUsed(respuesta, "parametros/plantilla_formulario.html")
        self.assertContains(respuesta, "data-editor-plantilla")
        self.assertNotContains(respuesta, 'name="codigo"')
        self.assertNotContains(respuesta, 'name="descripcion"')
        datos = {nombre.removeprefix("nueva-"): valor for nombre, valor in self.datos.items()}
        datos.update(categoria="calendario", activa="on")
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        plantilla = PlantillaNotificacion.objects.get()
        self.assertTrue(plantilla.codigo)
        codigo = plantilla.codigo
        plantilla.descripcion = "Descripción histórica"
        plantilla.save()
        datos["nombre"] = "Nombre actualizado"
        self.assertEqual(self.client.post(reverse("editar-parametro", args=("plantillas-mensajes", plantilla.pk)), datos).status_code, 302)
        plantilla.refresh_from_db()
        self.assertEqual(plantilla.codigo, codigo)
        self.assertEqual(plantilla.descripcion, "Descripción histórica")

    def test_fecha_conserva_codigo_y_descripcion_al_editar(self):
        fecha = FechaAdministrativa.objects.create(nombre="Anterior", codigo="referencia-estable", descripcion="Histórica", roles_destinatarios=["elector"])
        url = reverse("editar-parametro", args=("fechas-administrativas", fecha.pk))
        respuesta = self.client.get(url)
        for campo in ("codigo", "descripcion"):
            self.assertNotIn(campo, respuesta.context["formulario"].fields)
        respuesta = self.client.post(url, {"nombre": "Nuevo nombre", "estado_eleccion": "publicada", "roles_destinatarios": ["elector"], "alcance_todos_claustros": "on", "criterio_destinatarios": "todos_en_alcance", "activa": "on"})
        self.assertEqual(respuesta.status_code, 302)
        fecha.refresh_from_db()
        self.assertEqual(fecha.nombre, "Nuevo nombre")
        self.assertEqual(fecha.codigo, "referencia-estable")
        self.assertEqual(fecha.descripcion, "Histórica")

    def test_dialogo_no_pide_codigo_ni_descripcion(self):
        respuesta = self.client.get(reverse("crear-parametro", args=("fechas-administrativas",)))
        self.assertNotContains(respuesta, 'name="nueva-codigo"')
        self.assertNotContains(respuesta, 'name="nueva-descripcion"')
        self.assertContains(respuesta, 'name="nueva-nombre"')
