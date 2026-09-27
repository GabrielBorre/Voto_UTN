from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.usuarios.models import AsignacionRol


class JustificativosViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion)

    def test_bandeja_justificativos_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("bandeja-justificativos"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "justificativos/bandeja.html")

    def test_resume_y_distingue_visualmente_los_estados(self):
        claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes"),
        )
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="SIS"),
        )
        registro = RegistroPadron.objects.create(
            elector=Elector.objects.create(
                legajo="1001",
                nombre="Ana",
                apellido="Pérez",
                dni="12345678",
            ),
            eleccion=self.eleccion,
            eleccion_claustro_departamento=configuracion,
        )
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        for estado in (
            JustificativoAusencia.Estado.PENDIENTE,
            JustificativoAusencia.Estado.APROBADO,
            JustificativoAusencia.Estado.RECHAZADO,
        ):
            JustificativoAusencia.objects.create(
                registro_padron=registro,
                tipo=tipo,
                detalle=f"Solicitud {estado}",
                estado=estado,
            )
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-justificativos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Pendientes")
        self.assertContains(respuesta, "Aprobados")
        self.assertContains(respuesta, "Rechazados")
        self.assertContains(respuesta, 'class="pill info"', count=1)
        self.assertContains(respuesta, 'class="pill ok"', count=1)
        self.assertContains(respuesta, 'class="pill danger"', count=1)

    def test_gestionar_justificativos_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-justificativos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "justificativos/gestion.html")
        self.assertContains(respuesta, 'class="management-panel justifications-panel"')
        self.assertContains(respuesta, "Solicitudes recibidas")
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)
