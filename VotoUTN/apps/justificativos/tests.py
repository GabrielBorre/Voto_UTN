from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class JustificativosViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(nombre="Eleccion", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8), habilitada=False)
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion)

    def crear_justificativo(self):
        claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro,
            departamento=Departamento.objects.create(nombre="Electrónica", codigo="ELE"),
        )
        registro = RegistroPadron.objects.create(
            elector=Elector.objects.create(
                legajo="2001",
                nombre="Juan",
                apellido="Gómez",
                dni="23456789",
            ),
            eleccion=self.eleccion,
            eleccion_claustro_departamento=configuracion,
        )
        return JustificativoAusencia.objects.create(
            registro_padron=registro,
            tipo=TipoJustificativo.objects.create(nombre="Motivo laboral"),
            detalle="Detalle presentado por el elector.",
        )

    def crear_registro_padron(self, elector, eleccion):
        claustro = EleccionClaustro.objects.create(
            eleccion=eleccion,
            claustro=Claustro.objects.create(nombre=f"Estudiantes {eleccion.id}"),
        )
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro,
            departamento=Departamento.objects.create(nombre=f"Sistemas {eleccion.id}", codigo=f"D{eleccion.id}"),
        )
        return RegistroPadron.objects.create(
            elector=elector,
            eleccion=eleccion,
            eleccion_claustro_departamento=configuracion,
        )

    def crear_elector_con_padrones(self):
        elector = Elector.objects.create(legajo="3001", nombre="Ana", apellido="Pérez", dni="32345678")
        registro_anterior = self.crear_registro_padron(elector, self.eleccion)
        eleccion_reciente = Eleccion.objects.create(
            nombre="Elección reciente",
            fecha_inicio=make_aware(datetime(2026, 9, 3, 8)),
            fecha_fin=make_aware(datetime(2026, 9, 3, 16)),
            estado=Eleccion.Estado.CERRADA,
            habilitada=False,
        )
        registro_reciente = self.crear_registro_padron(elector, eleccion_reciente)
        usuario = get_user_model().objects.create_user(username="elector", password="clave")
        PerfilUsuario.objects.create(usuario=usuario, elector=elector)
        return usuario, registro_anterior, registro_reciente

    def test_mis_justificativos_muestra_la_eleccion_mas_reciente_sin_selector(self):
        usuario, _, registro_reciente = self.crear_elector_con_padrones()
        self.client.login(username=usuario.username, password="clave")

        respuesta = self.client.get(reverse("mis-justificativos"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["eleccion"], registro_reciente.eleccion)
        self.assertContains(respuesta, registro_reciente.eleccion.nombre)
        self.assertNotContains(respuesta, 'name="registro_padron"')

    def test_mis_justificativos_ignora_un_registro_padron_alterado_en_post(self):
        usuario, registro_anterior, registro_reciente = self.crear_elector_con_padrones()
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        self.client.login(username=usuario.username, password="clave")

        respuesta = self.client.post(
            reverse("mis-justificativos"),
            {
                "registro_padron": registro_anterior.id,
                "tipo": tipo.id,
                "detalle": "Ausencia por enfermedad.",
            },
        )

        self.assertRedirects(respuesta, reverse("mis-justificativos"))
        justificativo = JustificativoAusencia.objects.get(registro_padron__elector=registro_reciente.elector)
        self.assertEqual(justificativo.registro_padron, registro_reciente)

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

    def test_resolucion_separa_solicitud_formulario_y_acciones(self):
        justificativo = self.crear_justificativo()
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("resolver-justificativo", args=(justificativo.id,)))
        contenido = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "justificativos/resolver.html")
        self.assertContains(respuesta, "Solicitud presentada")
        self.assertContains(respuesta, "No se adjuntó documentación")
        self.assertContains(respuesta, 'id="formulario-resolucion-justificativo"')
        self.assertContains(respuesta, 'class="section-actions form-card-actions"')
        self.assertContains(respuesta, 'form="formulario-resolucion-justificativo"')
        self.assertContains(
            respuesta,
            reverse("gestionar-justificativos", args=(self.eleccion.id,)),
        )
        self.assertLess(
            contenido.index("Guardar resolución"),
            contenido.index("Volver a justificativos"),
        )

    def test_gestionar_justificativos_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-justificativos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "justificativos/gestion.html")
        self.assertContains(respuesta, 'class="management-panel justifications-panel"')
        self.assertContains(respuesta, "Solicitudes recibidas")
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)
