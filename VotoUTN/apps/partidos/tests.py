from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido, Partido


class PartidosBaseTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 9, 10, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion de prueba",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Estudiantes"),
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=Departamento.objects.create(nombre="Sistemas", codigo="SIS"),
        )
        self.partido = Partido.objects.create(nombre="Frente Universitario", sigla="FU")
        self.participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            partido=self.partido,
            numero_lista="10",
            nombre_lista="Universidad Abierta",
        )
        self.lista = ListaCandidatos.objects.create(
            participacion=self.participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Consejo Departamental",
        )


class CandidatoTests(PartidosBaseTests):
    def test_lista_rechaza_un_claustro_de_otra_eleccion(self):
        inicio = make_aware(datetime(2026, 9, 12, 8))
        otra_eleccion = Eleccion.objects.create(
            nombre="Otra eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        otro_alcance = EleccionClaustro.objects.create(
            eleccion=otra_eleccion,
            claustro=self.eleccion_claustro.claustro,
        )
        lista = ListaCandidatos(
            participacion=self.participacion,
            eleccion_claustro=otro_alcance,
            nombre="Alcance invalido",
        )

        with self.assertRaises(ValidationError):
            lista.full_clean()

    def test_candidato_puede_no_pertenecer_al_padron(self):
        candidato = Candidato(
            lista=self.lista,
            nombre="Persona Independiente",
            dni="30111222",
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        candidato.full_clean()
        candidato.save()

        self.assertIsNone(candidato.elector_id)

    def test_candidato_puede_vincularse_a_elector_sin_registro_en_el_padron(self):
        elector = Elector.objects.create(legajo="100", nombre="Maria Electoral", dni="30222333")
        candidato = Candidato(
            lista=self.lista,
            elector=elector,
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        candidato.full_clean()
        candidato.save()

        self.assertEqual(candidato.nombre, elector.nombre)
        self.assertEqual(candidato.dni, elector.dni)

    def test_elector_en_padron_de_otro_claustro_no_puede_integrar_la_lista(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        otra_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_claustro,
            departamento=Departamento.objects.create(nombre="Civil", codigo="CIV"),
        )
        elector = Elector.objects.create(legajo="101", nombre="Otro Elector", dni="30333444")
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=otra_configuracion,
        )
        candidato = Candidato(
            lista=self.lista,
            elector=elector,
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        with self.assertRaises(ValidationError):
            candidato.full_clean()

    def test_una_persona_no_puede_integrar_dos_listas_en_la_misma_eleccion(self):
        Candidato.objects.create(
            lista=self.lista,
            nombre="Persona Repetida",
            dni="30444555",
            cargo="Consejero",
            orden=1,
        )
        segundo_partido = Partido.objects.create(nombre="Espacio Academico")
        segunda_participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            partido=segundo_partido,
            numero_lista="20",
        )
        segunda_lista = ListaCandidatos.objects.create(
            participacion=segunda_participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Lista Alternativa",
        )
        duplicado = Candidato(
            lista=segunda_lista,
            nombre="Persona Repetida",
            dni="30444555",
            cargo="Consejero",
            orden=1,
        )

        with self.assertRaises(ValidationError):
            duplicado.full_clean()


class PartidosViewsTests(PartidosBaseTests):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username="admin-partidos", password="clave")
        self.client.login(username="admin-partidos", password="clave")

    def test_panel_requiere_permiso_y_usa_template_propietario(self):
        respuesta = self.client.get(reverse("gestionar-partidos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "partidos/gestion.html")

        sin_permiso = get_user_model().objects.create_user(username="sin-permiso")
        self.client.force_login(sin_permiso)
        respuesta = self.client.get(reverse("gestionar-partidos", args=(self.eleccion.id,)))
        self.assertEqual(respuesta.status_code, 403)

    def test_rechaza_numero_de_lista_repetido_sin_error_de_servidor(self):
        nuevo_partido = Partido.objects.create(nombre="Otro partido")

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "incorporar_partido",
                "participacion-partido": nuevo_partido.id,
                "participacion-numero_lista": self.participacion.numero_lista,
                "participacion-nombre_lista": "Numero repetido",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El numero de lista ya esta utilizado")
        self.assertFalse(ParticipacionPartido.objects.filter(partido=nuevo_partido, eleccion=self.eleccion).exists())

    def test_desactiva_candidato_mediante_post(self):
        candidato = Candidato.objects.create(
            lista=self.lista,
            nombre="Candidato activo",
            dni="30777666",
            cargo="Consejero",
            orden=1,
        )

        respuesta = self.client.post(
            reverse("cambiar-estado-candidato", args=(self.eleccion.id, candidato.id)),
            {"activo": "0"},
        )

        candidato.refresh_from_db()
        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(candidato.activo)

    def test_flujo_crea_partido_participacion_lista_y_candidato_independiente(self):
        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {"accion": "crear_partido", "partido-nombre": "Movimiento Tecnologico", "partido-sigla": "MT"},
        )
        self.assertRedirects(respuesta, reverse("gestionar-partidos", args=(self.eleccion.id,)))
        nuevo_partido = Partido.objects.get(sigla="MT")

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "incorporar_partido",
                "participacion-partido": nuevo_partido.id,
                "participacion-numero_lista": "30",
                "participacion-nombre_lista": "Innovacion",
            },
        )
        participacion = ParticipacionPartido.objects.get(partido=nuevo_partido, eleccion=self.eleccion)
        self.assertEqual(respuesta.status_code, 302)

        respuesta = self.client.post(
            reverse("detalle-participacion-partido", args=(self.eleccion.id, participacion.id)),
            {
                "nombre": "Lista de Sistemas",
                "eleccion_claustro": self.eleccion_claustro.id,
                "eleccion_claustro_departamento": self.configuracion.id,
            },
        )
        lista = ListaCandidatos.objects.get(participacion=participacion)
        self.assertEqual(respuesta.status_code, 302)

        respuesta = self.client.post(
            reverse("detalle-lista-candidatos", args=(self.eleccion.id, lista.id)),
            {
                "dni_elector": "",
                "nombre": "Candidata Externa",
                "dni": "30999888",
                "correo_electronico": "externa@example.com",
                "cargo": "Consejera",
                "tipo": Candidato.Tipo.TITULAR,
                "orden": 1,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Candidato.objects.filter(lista=lista, dni="30999888", elector__isnull=True).exists())
