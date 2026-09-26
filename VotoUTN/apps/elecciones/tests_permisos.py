from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.elecciones.models import Eleccion, FechaAdministrativaEleccion
from apps.parametros.models import Claustro, FechaAdministrativa, Sede, Turno
from apps.usuarios.models import AsignacionRol


class CreacionEleccionPorAdministradorJuntaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="administrador-junta")
        ahora = timezone.localdate()
        self.eleccion_asignada = Eleccion.objects.create(
            nombre="Eleccion asignada",
            fecha_inicio=ahora,
            fecha_fin=ahora + timedelta(days=1),
        )
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion_asignada,
        )
        self.sede = Sede.objects.create(nombre="Campus", activa=True)
        self.claustro = Claustro.objects.create(nombre="Docentes", activo=True)
        self.turno = Turno.objects.create(
            nombre="Manana",
            hora_inicio="08:00",
            hora_fin="12:00",
            activo=True,
        )
        self.client.force_login(self.usuario)

    def test_puede_abrir_el_formulario_de_nueva_eleccion(self):
        respuesta = self.client.get(reverse("crear-eleccion"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'type="date"', count=2)
        self.assertContains(respuesta, 'class="help-tip-icon"', count=3)
        self.assertContains(respuesta, 'role="tooltip"', count=3)
        self.assertContains(respuesta, "Nombre de la elección")
        self.assertContains(respuesta, "Elección de representantes al Consejo Directivo 2027")
        self.assertContains(respuesta, "Inicio del proceso electoral")
        self.assertContains(respuesta, "Fin del proceso electoral")
        self.assertContains(respuesta, "No corresponde al día de votación", count=2)
        self.assertNotContains(respuesta, "Turnos de trabajo")
        self.assertContains(respuesta, 'class="select-all"', count=2)
        self.assertContains(respuesta, 'class="field checkbox-group"', count=2)

    def test_al_crear_eleccion_queda_asignado_como_administrador(self):
        inicio = timezone.localdate() + timedelta(days=30)
        fin = inicio + timedelta(days=1)

        respuesta = self.client.post(
            reverse("crear-eleccion"),
            {
                "nombre": "Nueva eleccion",
                "fecha_inicio": inicio.isoformat(),
                "fecha_fin": fin.isoformat(),
                "sedes": [self.sede.pk],
                "claustros": [self.claustro.pk],
            },
        )

        eleccion = Eleccion.objects.get(nombre="Nueva eleccion")
        self.assertRedirects(
            respuesta,
            reverse("configurar-eleccion", args=(eleccion.pk,)),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            AsignacionRol.objects.filter(
                usuario=self.usuario,
                rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
                eleccion=eleccion,
                sede__isnull=True,
                mesa__isnull=True,
                activo=True,
            ).exists()
        )

    def test_configura_las_fechas_administrativas_en_la_eleccion(self):
        definicion = FechaAdministrativa.objects.create(
            codigo="publicacion-padron-prueba",
            nombre="Publicacion de padron",
            roles_destinatarios=[FechaAdministrativa.RolDestinatario.ELECTOR],
        )

        respuesta = self.client.post(
            reverse("gestionar-fechas-administrativas", args=(self.eleccion_asignada.pk,)),
            {
                f"fecha_{definicion.pk}_seleccionada": "on",
                f"fecha_{definicion.pk}_valor": self.eleccion_asignada.fecha_inicio.isoformat(),
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("gestionar-fechas-administrativas", args=(self.eleccion_asignada.pk,)),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            FechaAdministrativaEleccion.objects.filter(
                eleccion=self.eleccion_asignada,
                fecha_administrativa=definicion,
                fecha=self.eleccion_asignada.fecha_inicio,
            ).exists()
        )

    def test_la_configuracion_enlaza_un_panel_independiente_de_fechas(self):
        respuesta = self.client.get(
            reverse("configurar-eleccion", args=(self.eleccion_asignada.pk,)),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Fechas administrativas")
        self.assertContains(
            respuesta,
            reverse("gestionar-fechas-administrativas", args=(self.eleccion_asignada.pk,)),
        )
        self.assertNotContains(respuesta, "Guardar fechas administrativas")

    def test_el_periodo_puede_comenzar_y_terminar_el_mismo_dia(self):
        eleccion = Eleccion(
            nombre="Proceso de un dia",
            fecha_inicio=timezone.localdate(),
            fecha_fin=timezone.localdate(),
        )

        eleccion.full_clean()

    def test_usuario_sin_rol_no_puede_crear_eleccion(self):
        usuario_sin_rol = get_user_model().objects.create_user(username="sin-rol")
        self.client.force_login(usuario_sin_rol)

        respuesta = self.client.get(reverse("crear-eleccion"))

        self.assertEqual(respuesta.status_code, 403)
