from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionClaustroTurno,
)
from apps.mesas.forms import FormularioGenerarMesas
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol


class MesasTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.sede = Sede.objects.create(nombre="Sede Central")
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.turno = Turno.objects.create(
            nombre="Manana",
            hora_inicio=time(8),
            hora_fin=time(12),
        )
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=self.claustro,
        )
        EleccionClaustroTurno.objects.create(eleccion_claustro=eleccion_claustro, turno=self.turno)
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="SIS"),
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

    def test_formulario_genera_mesas_numeradas_sin_turno_de_elector(self):
        formulario = FormularioGenerarMesas(
            eleccion=self.eleccion,
            data={
                "configuracion": self.configuracion.id,
                "sede": self.sede.id,
                "cantidad": 2,
            },
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.generar()
        self.assertEqual(
            list(self.eleccion.mesas.values_list("numero", flat=True)),
            [1, 2],
        )
        self.assertFalse(hasattr(self.eleccion.mesas.first(), "turno_id"))

    def test_gestionar_mesas_conserva_la_ruta_y_requiere_permiso(self):
        usuario = get_user_model().objects.create_user(
            username="administrador",
            password="clave",
        )
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.login(username="administrador", password="clave")
        primera_mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            generada_automaticamente=True,
        )
        Mesa.objects.create(
            eleccion=self.eleccion,
            numero=2,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            generada_automaticamente=False,
        )
        for numero in range(3, 21):
            Mesa.objects.create(
                eleccion=self.eleccion,
                numero=numero,
                eleccion_claustro_departamento=self.configuracion,
                sede=self.sede,
                generada_automaticamente=True,
            )
        registro = RegistroPadron.objects.create(
            elector=Elector.objects.create(legajo="1001", dni="40100100", nombre="Ana"),
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
        )
        AsignacionMesa.objects.create(registro_padron=registro, mesa=primera_mesa)

        url = reverse("gestionar-mesas", args=(self.eleccion.id,))
        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "mesas/gestion.html")
        self.assertContains(respuesta, 'class="management-panel tables-panel"')
        self.assertContains(respuesta, "Total de mesas")
        self.assertContains(respuesta, "Claustros con mesas")
        self.assertContains(respuesta, "Sedes utilizadas")
        self.assertContains(respuesta, "Cantidad de electores")
        self.assertContains(respuesta, "SIS-01")
        self.assertContains(respuesta, "SIS-20")
        self.assertContains(respuesta, ">1</td>")
        contenido = respuesta.content.decode()
        self.assertLess(contenido.index("ordenar=claustro"), contenido.index("ordenar=numero"))
        self.assertNotContains(respuesta, "Manuales")
        self.assertContains(respuesta, "Registrada previamente")
        self.assertContains(respuesta, 'class="pill info"', count=19)
        self.assertContains(respuesta, 'class="pill gray"', count=1)
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)

        respuesta_ordenada = self.client.get(url, {"ordenar": "numero", "direccion": "desc"})
        contenido_ordenado = respuesta_ordenada.content.decode()
        self.assertLess(contenido_ordenado.index("SIS-20"), contenido_ordenado.index("SIS-01"))

        sin_permiso = get_user_model().objects.create_user(
            username="sin_permiso",
            password="clave",
        )
        self.client.force_login(sin_permiso)

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 403)

    def test_muestra_el_alcance_interno_sin_departamento(self):
        claustro = Claustro.objects.create(
            nombre="No docentes",
            organizacion_departamentos=Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=claustro,
            organizacion_departamentos=Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=None,
        )
        Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=alcance,
            sede=self.sede,
            generada_automaticamente=True,
        )
        usuario = get_user_model().objects.create_user(username="administrador_no_docente")
        AsignacionRol.objects.create(
            usuario=usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("gestionar-mesas", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No docentes")
        self.assertContains(respuesta, "Sin distinción por departamento")
