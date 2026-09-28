from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion
from apps.parametros.models import Claustro, Sede, Turno
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import puede_administrar_elecciones, puede_crear_elecciones


class CrearEleccionAdministradorJuntaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="administrador-junta",
            password="clave",
        )
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion_asignada = Eleccion.objects.create(
            nombre="Elección asignada",
            fecha_inicio=inicio,
            fecha_fin=make_aware(datetime(2026, 8, 3, 18)),
        )
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion_asignada,
        )
        self.sede = Sede.objects.create(nombre="Sede central")
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.turno = Turno.objects.create(
            nombre="Mañana",
            hora_inicio=time(8),
            hora_fin=time(12),
        )
        self.client.force_login(self.usuario)

    def test_administrador_junta_puede_crear_eleccion_sin_eleccion_en_el_permiso(self):
        self.assertTrue(puede_crear_elecciones(self.usuario))
        self.assertFalse(puede_administrar_elecciones(self.usuario))
        self.assertTrue(puede_administrar_elecciones(self.usuario, self.eleccion_asignada))

        respuesta = self.client.post(
            reverse("crear-eleccion"),
            {
                "nombre": "Elección nueva",
                "fecha_inicio": "2026-09-01T08:00",
                "fecha_fin": "2026-09-01T18:00",
                "sedes": [self.sede.id],
                "claustros": [self.claustro.id],
                "turnos": [self.turno.id],
            },
        )

        eleccion_nueva = Eleccion.objects.get(nombre="Elección nueva")
        self.assertRedirects(
            respuesta,
            reverse("preparar-eleccion", args=[eleccion_nueva.id]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            AsignacionRol.objects.filter(
                usuario=self.usuario,
                rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
                eleccion=eleccion_nueva,
                activo=True,
            ).exists()
        )
        self.assertTrue(puede_administrar_elecciones(self.usuario, eleccion_nueva))

    def test_administrador_junta_ve_creacion_pero_no_gestion_global(self):
        respuesta = self.client.get(reverse("lista-elecciones"))

        self.assertContains(respuesta, reverse("crear-eleccion"))
        self.assertNotContains(respuesta, reverse("historial-elecciones"))
        self.assertEqual(self.client.get(reverse("gestionar-elecciones")).status_code, 403)

    def test_administrativo_junta_no_puede_crear_elecciones(self):
        self.usuario.asignaciones_rol.all().delete()
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=self.eleccion_asignada,
        )

        self.assertFalse(puede_crear_elecciones(self.usuario))
        self.assertEqual(self.client.get(reverse("crear-eleccion")).status_code, 403)
