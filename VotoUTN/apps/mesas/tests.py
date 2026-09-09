from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionTurno,
)
from apps.mesas.forms import FormularioGenerarMesas
from apps.mesas.models import Mesa
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
        EleccionTurno.objects.create(eleccion=self.eleccion, turno=self.turno)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=self.claustro,
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="SIS"),
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )

    def test_formulario_genera_mesas_numeradas_y_valida_turno_habilitado(self):
        formulario = FormularioGenerarMesas(
            eleccion=self.eleccion,
            data={
                "configuracion": self.configuracion.id,
                "sede": self.sede.id,
                "turno": self.turno.id,
                "cantidad": 2,
            },
        )

        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.generar()
        self.assertEqual(
            list(self.eleccion.mesas.values_list("numero", flat=True)),
            [1, 2],
        )

        turno_ajeno = Turno.objects.create(
            nombre="Tarde",
            hora_inicio=time(13),
            hora_fin=time(18),
        )
        mesa = Mesa(
            eleccion=self.eleccion,
            numero=3,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            turno=turno_ajeno,
        )
        with self.assertRaises(ValidationError):
            mesa.full_clean()

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

        respuesta = self.client.get(reverse("gestionar-mesas", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "mesas/gestion.html")

        sin_permiso = get_user_model().objects.create_user(
            username="sin_permiso",
            password="clave",
        )
        self.client.force_login(sin_permiso)

        respuesta = self.client.get(reverse("gestionar-mesas", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 403)
