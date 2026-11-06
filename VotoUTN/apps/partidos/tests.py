from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import make_aware

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ImportacionCandidaturas,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    Partido,
    PuestoEleccion,
)
from apps.partidos.forms import FormularioPuestoEleccion
from apps.usuarios.models import AsignacionRol


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
            codigo_presentacion="EST-10",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="10",
            nombre_lista="Universidad Abierta",
        )
        self.organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        self.puesto = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Consejero/a",
            permite_filtrar_departamentos=True,
        )
        self.puesto_eleccion = PuestoEleccion.objects.create(
            puesto=self.puesto,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            cantidad_titulares=3,
            cantidad_suplentes=3,
        )
        self.lista = ListaCandidatos.objects.create(
            participacion=self.participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Consejo Departamental",
            puesto_eleccion=self.puesto_eleccion,
        )

    def crear_elector_padron(self, *, dni, legajo=None, configuracion=None, activo=True):
        elector = Elector.objects.create(
            legajo=legajo or dni, nombre="Ana", apellido="Pérez", dni=dni,
        )
        RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=configuracion or self.configuracion, activo=activo,
        )
        return elector


class CandidatoTests(PartidosBaseTests):
    def test_lista_rechaza_un_claustro_de_otra_eleccion(self):
        inicio = make_aware(datetime(2026, 9, 12, 8))
        otra_eleccion = Eleccion.objects.create(
            nombre="Otra eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            estado=Eleccion.Estado.FINALIZADA,
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

    def test_candidato_no_puede_quedar_fuera_del_padron(self):
        candidato = Candidato(
            lista=self.lista,
            nombre="Persona Independiente",
            dni="30111222",
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        with self.assertRaises(ValidationError):
            candidato.full_clean()

    def test_candidato_rechaza_elector_sin_registro_en_el_padron(self):
        elector = Elector.objects.create(legajo="100", nombre="Maria Electoral", dni="30222333")
        candidato = Candidato(
            lista=self.lista,
            elector=elector,
            cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        with self.assertRaises(ValidationError):
            candidato.full_clean()

    def test_candidato_toma_identidad_del_elector_del_padron(self):
        elector = self.crear_elector_padron(dni="30222334")
        candidato = Candidato(
            lista=self.lista, elector=elector, cargo="Consejero/a", tipo=Candidato.Tipo.TITULAR, orden=1,
        )

        candidato.full_clean()
        candidato.save()

        self.assertEqual(candidato.nombre, elector.nombre_completo)
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

    def test_una_persona_puede_integrar_mas_de_una_candidatura_en_la_eleccion(self):
        elector = self.crear_elector_padron(dni="30444555")
        Candidato.objects.create(
            lista=self.lista,
            elector=elector, nombre=elector.nombre_completo, dni=elector.dni,
            cargo="Consejero",
            orden=1,
        )
        segundo_partido = Partido.objects.create(nombre="Espacio Academico")
        segunda_participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            partido=segundo_partido,
            codigo_presentacion="EST-20",
            eleccion_claustro=self.eleccion_claustro,
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
            elector=elector,
            cargo="Consejero",
            orden=1,
        )

        duplicado.full_clean()
        duplicado.save()
        self.assertEqual(Candidato.objects.filter(dni="30444555").count(), 2)

    def test_candidato_rechaza_orden_superior_al_puesto_configurado(self):
        elector = self.crear_elector_padron(dni="30444556")
        candidato = Candidato(
            lista=self.lista,
            elector=elector,
            tipo=Candidato.Tipo.TITULAR,
            orden=4,
        )

        with self.assertRaises(ValidationError):
            candidato.full_clean()


class PartidosViewsTests(PartidosBaseTests):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(username="admin-partidos", password="clave")
        self.client.login(username="admin-partidos", password="clave")

    def test_panel_requiere_permiso_y_usa_template_propietario(self):
        administrador = get_user_model().objects.create_user(username="admin-junta-partidos")
        AsignacionRol.objects.create(
            usuario=administrador,
            eleccion=self.eleccion,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        )
        self.client.force_login(administrador)
        respuesta = self.client.get(reverse("gestionar-partidos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "partidos/gestion.html")
        self.assertContains(
            respuesta,
            '<a class="active" href="/gestion/elecciones/">Configurar elección</a>',
        )
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)
        self.assertContains(respuesta, "Gestión por claustro")
        self.assertContains(respuesta, f"?claustro={self.eleccion_claustro.id}")
        self.assertNotContains(respuesta, "Crear una lista")

        respuesta_claustro = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}"
        )
        self.assertEqual(
            respuesta_claustro.context["formulario_participacion"]["eleccion_claustro"].value(),
            self.eleccion_claustro.id,
        )
        puestos_disponibles = respuesta_claustro.context["formulario_participacion"].fields[
            "puestos_eleccion"
        ].queryset
        self.assertIn(self.puesto_eleccion, puestos_disponibles)
        self.assertContains(respuesta_claustro, 'class="management-panel candidaturas-panel"')
        self.assertContains(respuesta_claustro, "Crear lista")
        self.assertContains(respuesta_claustro, "Cargar puesto")
        self.assertContains(respuesta_claustro, "Cargar candidatos")
        self.assertNotContains(respuesta_claustro, "Habilitar un puesto")

        otra_participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion="DOC-10",
            eleccion_claustro=EleccionClaustro.objects.create(
                eleccion=self.eleccion,
                claustro=Claustro.objects.create(nombre="Docentes"),
            ),
            numero_lista="10",
            nombre_lista="Lista docente",
        )
        respuesta_pestana_candidatos = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=candidatos"
        )
        self.assertEqual(respuesta_pestana_candidatos.context["pestana"], "candidatos")
        self.assertContains(respuesta_pestana_candidatos, "Universidad Abierta")
        self.assertContains(respuesta_pestana_candidatos, "Cargar candidatos")
        self.assertContains(
            respuesta_pestana_candidatos,
            reverse("detalle-participacion-partido", args=(self.eleccion.id, self.participacion.id)),
        )
        self.assertContains(
            respuesta_pestana_candidatos,
            reverse("editar-participacion-partido", args=(self.eleccion.id, self.participacion.id)),
        )
        self.assertNotContains(respuesta_pestana_candidatos, otra_participacion.nombre_lista)
        self.assertNotContains(respuesta_pestana_candidatos, "Crear una lista")

        respuesta_pestana_puesto = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto"
        )
        self.assertEqual(respuesta_pestana_puesto.context["pestana"], "puesto")
        self.assertContains(respuesta_pestana_puesto, "Cargar puesto")
        self.assertContains(respuesta_pestana_puesto, "Puestos habilitados")
        self.assertNotContains(respuesta_pestana_puesto, "Cargar candidatos</h2>")
        self.assertNotContains(respuesta, "Carga manual")

        sin_permiso = get_user_model().objects.create_user(username="sin-permiso")
        self.client.force_login(sin_permiso)
        respuesta = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}"
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_cambiar_estado_puesto_regresa_a_la_pestana_del_claustro(self):
        respuesta = self.client.post(
            f"{reverse('cambiar-estado-puesto-eleccion', args=(self.eleccion.id, self.puesto_eleccion.id))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto",
            {"activo": "0"},
        )

        self.assertRedirects(
            respuesta,
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto",
        )
        self.puesto_eleccion.refresh_from_db()
        self.assertFalse(self.puesto_eleccion.activo)

    def test_puesto_sin_listas_se_puede_eliminar_desde_su_pestana(self):
        puesto = PuestoEleccion.objects.create(
            puesto=CargoElectivo.objects.create(organo=self.organo, nombre="Puesto eliminable"),
            eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1,
        )

        respuesta = self.client.post(
            f"{reverse('eliminar-puesto-eleccion', args=(self.eleccion.id, puesto.id))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto",
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto",
        )
        self.assertFalse(PuestoEleccion.objects.filter(pk=puesto.pk).exists())
        self.assertContains(self.client.get(respuesta.url), "El puesto fue eliminado.")

    def test_puesto_asociado_a_lista_no_se_puede_eliminar(self):
        respuesta = self.client.post(
            f"{reverse('eliminar-puesto-eleccion', args=(self.eleccion.id, self.puesto_eleccion.id))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto",
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto",
        )
        self.assertTrue(PuestoEleccion.objects.filter(pk=self.puesto_eleccion.pk).exists())
        self.assertContains(self.client.get(respuesta.url), "No se puede eliminar el puesto")

    def test_ingresar_a_partidos_no_crea_puestos_departamentales_predeterminados(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        configuracion_graduados = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_claustro,
            departamento=self.configuracion.departamento,
        )
        configuracion_docentes = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_docente,
            departamento=self.configuracion.departamento,
        )

        respuesta = self.client.get(reverse("gestionar-partidos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, f"?claustro={self.eleccion_claustro.id}")
        self.assertContains(respuesta, f"?claustro={otro_claustro.id}")
        self.assertNotContains(respuesta, "Crear una lista")
        self.assertFalse(
            PuestoEleccion.objects.filter(
                puesto__nombre="Consejero/a departamental",
            ).exists()
        )

    def test_puestos_se_muestran_agrupados_por_claustro_y_tipo_de_organo(self):
        organo_directivo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        organo_dasuten = OrganoElectivo.objects.create(nombre="Consejo DASUTeN")
        cargo_directivo = CargoElectivo.objects.create(
            organo=organo_directivo,
            nombre="Consejero/a directivo/a",
        )
        cargo_dasuten = CargoElectivo.objects.create(
            organo=organo_dasuten,
            nombre="Consejero/a DASUTeN",
        )
        PuestoEleccion.objects.create(
            puesto=cargo_directivo,
            eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=2,
        )
        PuestoEleccion.objects.create(
            puesto=cargo_dasuten,
            eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1,
        )
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        puesto_docente = PuestoEleccion.objects.create(
            puesto=cargo_directivo,
            eleccion_claustro=claustro_docente,
            cantidad_titulares=2,
        )

        respuesta = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}"
        )

        self.assertEqual(respuesta.status_code, 200)
        grupo = next(
            grupo for grupo in respuesta.context["puestos_seleccionables_por_claustro"]
            if grupo["nombre"] == "Estudiantes"
        )
        self.assertEqual(
            [categoria["nombre"] for categoria in grupo["categorias"]],
            ["Departamentales", "Directivos", "DASUTeN"],
        )
        self.assertContains(respuesta, "<summary>Departamentales")
        self.assertContains(respuesta, "<summary>Directivos")
        self.assertContains(respuesta, "<summary>DASUTeN")
        self.assertNotContains(respuesta, "<summary>Docentes")
        self.assertContains(
            respuesta,
            f'name="presentacion-puestos_eleccion" value="{self.puesto_eleccion.id}"',
        )
        self.assertNotContains(
            respuesta,
            f'name="presentacion-puestos_eleccion" value="{puesto_docente.id}"',
        )
        contenido = respuesta.content.decode()
        inicio_listas = contenido.index("Crear una lista")
        self.assertLess(
            contenido.index("Puestos de la lista"),
            contenido.index("<summary>Departamentales"),
        )
        self.assertNotContains(respuesta, "data-puestos-claustro")
        self.assertNotContains(respuesta, "puestos-lista-claustro.js")
        self.assertNotIn(" hidden>", contenido)
        respuesta_puestos = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto"
        )
        self.assertContains(respuesta_puestos, "Puestos habilitados")
        self.assertContains(respuesta_puestos, str(self.puesto_eleccion.puesto))
        tabla_puestos = respuesta_puestos.content.decode().split("Puestos habilitados", 1)[1]
        self.assertNotIn("Docentes", tabla_puestos)

    def test_admite_numero_repetido_en_presentaciones_independientes(self):
        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}",
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": self.participacion.numero_lista,
                "presentacion-nombre_lista": "Número repetido permitido",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        nueva_presentacion = ParticipacionPartido.objects.get(
            eleccion=self.eleccion,
            nombre_lista="Número repetido permitido",
        )
        self.assertTrue(nueva_presentacion.codigo_presentacion.startswith("MAN-"))
        self.assertNotEqual(nueva_presentacion.codigo_presentacion, self.participacion.codigo_presentacion)
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, nueva_presentacion.id))}#candidaturas",
        )
        self.assertEqual(
            ParticipacionPartido.objects.filter(eleccion=self.eleccion, numero_lista="10").count(),
            2,
        )

    def test_crea_lista_asociando_puestos_y_abre_directamente_sus_candidatos(self):
        call_command("habilitar_puestos_departamentales", str(self.eleccion.pk), verbosity=0)
        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}",
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "31",
                "presentacion-nombre_lista": "Lista integrada",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
                "presentacion-puestos_eleccion": [self.puesto_eleccion.id],
            },
        )

        participacion = ParticipacionPartido.objects.get(nombre_lista="Lista integrada")
        lista = ListaCandidatos.objects.get(participacion=participacion)
        self.assertEqual(lista.puesto_eleccion, self.puesto_eleccion)
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}"
            f"?puesto={lista.id}#candidaturas",
        )
        detalle = self.client.get(
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}"
            f"?puesto={lista.id}"
        )
        self.assertContains(detalle, "Puestos asociados a esta lista")
        self.assertNotContains(detalle, "Puestos por los que se presenta")
        self.assertContains(detalle, "Agregar otro puesto (opcional)")
        self.assertContains(detalle, "Agregar puesto a la lista")

    def test_puede_agregar_otro_puesto_despues_de_crear_la_lista(self):
        segunda_configuracion = PuestoEleccion.objects.create(
            puesto=CargoElectivo.objects.create(
                organo=self.organo,
                nombre="Consejero/a alternativo/a",
            ),
            eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1,
        )
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion="MAN-PUESTO-ADICIONAL",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="36",
            nombre_lista="Lista con puesto adicional",
        )
        ListaCandidatos.objects.create(
            participacion=participacion,
            eleccion_claustro=self.eleccion_claustro,
            nombre="Consejero/a",
            puesto_eleccion=self.puesto_eleccion,
        )

        respuesta = self.client.post(
            reverse("detalle-participacion-partido", args=(self.eleccion.id, participacion.id)),
            {
                "accion": "vincular_puesto",
                "puesto_eleccion": segunda_configuracion.id,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            ListaCandidatos.objects.filter(
                participacion=participacion,
                puesto_eleccion=segunda_configuracion,
            ).exists()
        )

    def test_crea_un_puesto_nuevo_y_lo_asocia_a_la_lista_en_el_mismo_envio(self):
        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "33",
                "presentacion-nombre_lista": "Lista con puesto nuevo",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
                "presentacion-puesto_nuevo": self.puesto.id,
                "presentacion-cantidad_titulares_nueva": "2",
                "presentacion-cantidad_suplentes_nueva": "1",
            },
        )

        participacion = ParticipacionPartido.objects.get(nombre_lista="Lista con puesto nuevo")
        configuracion = PuestoEleccion.objects.get(
            eleccion_claustro=self.eleccion_claustro,
            puesto=self.puesto,
            eleccion_claustro_departamento__isnull=True,
        )
        lista = ListaCandidatos.objects.get(participacion=participacion)
        self.assertEqual(lista.puesto_eleccion, configuracion)
        self.assertEqual(configuracion.cantidad_titulares, 2)
        self.assertEqual(configuracion.cantidad_suplentes, 1)
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}"
            f"?puesto={lista.id}#candidaturas",
        )

    def test_puesto_sin_filtro_de_claustros_se_habilita_para_todos(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        cargo = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante general",
            permite_filtrar_claustros=False,
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "35",
                "presentacion-nombre_lista": "Lista para todos",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
                "presentacion-puesto_nuevo": cargo.id,
                "presentacion-cantidad_titulares_nueva": "1",
                "presentacion-cantidad_suplentes_nueva": "1",
            },
        )

        participacion = ParticipacionPartido.objects.get(nombre_lista="Lista para todos")
        configuraciones = PuestoEleccion.objects.filter(puesto=cargo)
        self.assertEqual(
            set(configuraciones.values_list("eleccion_claustro_id", flat=True)),
            {self.eleccion_claustro.id, otro_claustro.id},
        )
        self.assertEqual(
            ListaCandidatos.objects.get(participacion=participacion).puesto_eleccion,
            configuraciones.get(eleccion_claustro=self.eleccion_claustro),
        )
        self.assertEqual(respuesta.status_code, 302)

    def test_no_crea_lista_si_faltan_titulares_del_puesto_nuevo(self):
        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}",
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "34",
                "presentacion-nombre_lista": "Lista incompleta",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
                "presentacion-puesto_nuevo": self.puesto.id,
                "presentacion-cantidad_suplentes_nueva": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Indicá la cantidad de titulares")
        self.assertFalse(ParticipacionPartido.objects.filter(nombre_lista="Lista incompleta").exists())

    def test_puesto_nuevo_requiere_al_menos_un_suplente(self):
        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}",
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "37",
                "presentacion-nombre_lista": "Lista sin suplente",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
                "presentacion-puesto_nuevo": self.puesto.id,
                "presentacion-cantidad_titulares_nueva": "1",
                "presentacion-cantidad_suplentes_nueva": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("cantidad_suplentes_nueva", respuesta.context["formulario_participacion"].errors)
        self.assertFalse(ParticipacionPartido.objects.filter(nombre_lista="Lista sin suplente").exists())

    def test_formularios_de_puestos_inician_titulares_y_suplentes_en_uno(self):
        formulario_habilitacion = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}"
            f"?claustro={self.eleccion_claustro.id}&pestana=puesto"
        ).context["formulario_puesto"]
        formulario_edicion = self.client.get(
            reverse("editar-puesto-eleccion", args=(self.eleccion.id, self.puesto_eleccion.id))
        ).context["formulario"]
        formulario_crear_lista = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}"
        ).context["formulario_participacion"]

        for formulario in (formulario_habilitacion, formulario_edicion):
            with self.subTest(formulario=formulario.__class__.__name__):
                self.assertEqual(formulario.fields["cantidad_titulares"].min_value, 1)
                self.assertEqual(formulario.fields["cantidad_suplentes"].min_value, 1)
                self.assertEqual(formulario.fields["cantidad_titulares"].widget.attrs["min"], 1)
                self.assertEqual(formulario.fields["cantidad_suplentes"].widget.attrs["min"], 1)
        self.assertEqual(formulario_habilitacion["cantidad_titulares"].value(), 1)
        self.assertEqual(formulario_habilitacion["cantidad_suplentes"].value(), 1)
        self.assertEqual(formulario_crear_lista["cantidad_titulares_nueva"].value(), 1)
        self.assertEqual(formulario_crear_lista["cantidad_suplentes_nueva"].value(), 1)

    def test_no_asocia_a_una_lista_un_puesto_de_otro_claustro(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        otro_puesto = PuestoEleccion.objects.create(
            puesto=self.puesto,
            eleccion_claustro=otro_claustro,
            cantidad_titulares=1,
        )

        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}",
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "32",
                "presentacion-nombre_lista": "Lista inválida",
                "presentacion-apoderado_nombre": "Persona Apoderada",
                "presentacion-apoderado_email": "",
                "presentacion-puestos_eleccion": [otro_puesto.id],
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Seleccione una opción válida")
        self.assertFalse(ParticipacionPartido.objects.filter(nombre_lista="Lista inválida").exists())

    def test_carga_manual_muestra_claustro_y_solo_puestos_de_su_alcance(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        otro_puesto = PuestoEleccion.objects.create(
            puesto=self.puesto,
            eleccion_claustro=otro_claustro,
            cantidad_titulares=1,
            cantidad_suplentes=0,
        )

        respuesta_gestion = self.client.get(
            f"{reverse('gestionar-partidos', args=(self.eleccion.id,))}?claustro={self.eleccion_claustro.id}"
        )
        campo_claustro = respuesta_gestion.context["formulario_participacion"].fields["eleccion_claustro"]
        self.assertTrue(campo_claustro.required)
        self.assertIn((self.eleccion_claustro.id, "Estudiantes"), list(campo_claustro.choices))

        presentacion_sin_puestos = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion="EST-SIN-PUESTOS",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="20",
            nombre_lista="Lista de prueba",
        )
        respuesta_detalle = self.client.get(
            reverse("detalle-participacion-partido", args=(self.eleccion.id, presentacion_sin_puestos.id))
        )
        puestos = respuesta_detalle.context["formulario"].fields["puesto_eleccion"].queryset
        self.assertIn(self.puesto_eleccion, puestos)
        self.assertNotIn(otro_puesto, puestos)
        self.assertContains(respuesta_detalle, "Puestos por los que se presenta")
        self.assertContains(respuesta_detalle, "Agregar puesto a la lista")

    def test_edita_lista_sin_cambiar_claustro_con_puestos_vinculados(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Docentes"),
        )
        destino = reverse("editar-participacion-partido", args=(self.eleccion.id, self.participacion.id))
        respuesta = self.client.get(destino)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El claustro no puede cambiarse")

        respuesta = self.client.post(destino, {
            "eleccion_claustro": otro_claustro.id,
            "numero_lista": "42",
            "nombre_lista": "Lista actualizada",
            "apoderado_nombre": "Nueva apoderada",
            "apoderado_email": "apoderada@example.com",
        })
        self.assertRedirects(respuesta, reverse("gestionar-partidos", args=(self.eleccion.id,)))
        self.participacion.refresh_from_db()
        self.assertEqual(self.participacion.nombre_lista, "Lista actualizada")
        self.assertEqual(self.participacion.numero_lista, "42")
        self.assertEqual(self.participacion.eleccion_claustro, self.eleccion_claustro)
        self.assertEqual(self.lista.puesto_eleccion, self.puesto_eleccion)

    def test_puesto_actual_se_identifica_sin_boton_redundante(self):
        otro_cargo = CargoElectivo.objects.create(
            organo=self.organo, nombre="Representante", permite_filtrar_departamentos=False,
        )
        otro_puesto = PuestoEleccion.objects.create(
            puesto=otro_cargo, eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1, cantidad_suplentes=0,
        )
        otra_asociacion = ListaCandidatos.objects.create(
            participacion=self.participacion, eleccion_claustro=self.eleccion_claustro,
            nombre="Representante", puesto_eleccion=otro_puesto,
        )
        destino = reverse("detalle-participacion-partido", args=(self.eleccion.id, self.participacion.id))
        respuesta = self.client.get(f"{destino}?puesto={self.lista.id}")

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Seleccionado", count=1)
        self.assertContains(respuesta, "Editar candidatos", count=1)
        self.assertContains(respuesta, f"?puesto={otra_asociacion.id}#candidaturas")
        self.assertContains(respuesta, 'class="candidaturas-puesto-seleccionado"', count=1)

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
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}?puesto={self.lista.id}#candidaturas",
        )
        self.assertFalse(candidato.activo)

    def test_edita_candidato_en_la_misma_pantalla(self):
        elector = self.crear_elector_padron(dni="30777667")
        candidato = Candidato.objects.create(
            lista=self.lista, elector=elector, nombre="Nombre anterior", dni=elector.dni, cargo="Consejero",
            tipo=Candidato.Tipo.TITULAR, orden=1,
        )
        destino = (
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={self.lista.id}&editar={candidato.id}"
        )
        respuesta = self.client.get(destino)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Editar candidato")

        respuesta = self.client.post(destino, {
            "accion": "guardar_candidato", "tipo_documento": "DNI", "documento": "30777667",
            "tipo": Candidato.Tipo.TITULAR, "orden": 1,
        })
        candidato.refresh_from_db()
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={self.lista.id}&pestana_candidatos=manual#candidaturas",
        )
        self.assertEqual(candidato.nombre, elector.nombre_completo)

    def test_flujo_crea_presentacion_lista_y_candidato_del_padron(self):
        call_command("habilitar_puestos_departamentales", str(self.eleccion.pk), verbosity=0)
        elector = self.crear_elector_padron(dni="30999888")
        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.id,)),
            {
                "accion": "crear_presentacion",
                "presentacion-eleccion_claustro": self.eleccion_claustro.id,
                "presentacion-numero_lista": "30",
                "presentacion-nombre_lista": "Innovación",
                "presentacion-apoderado_nombre": "Ana Apoderada",
                "presentacion-apoderado_email": "ana@example.com",
            },
        )
        participacion = ParticipacionPartido.objects.get(nombre_lista="Innovación", eleccion=self.eleccion)
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}#candidaturas",
        )

        respuesta = self.client.post(
            reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id)),
            {
                "accion": "vincular_puesto",
                "puesto_eleccion": self.puesto_eleccion.id,
            },
        )
        lista = ListaCandidatos.objects.get(participacion=participacion)
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}?puesto={lista.id}#candidaturas",
        )
        detalle = self.client.get(
            reverse("detalle-participacion-partido", args=(self.eleccion.id, participacion.id)),
            {"puesto": lista.id},
        )
        self.assertContains(detalle, "Puestos asociados a esta lista")
        self.assertContains(detalle, "Agregar otro puesto (opcional)")
        self.assertContains(detalle, "Agregar puesto a la lista")

        respuesta = self.client.post(
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}?puesto={lista.id}",
            {
                "accion": "agregar_candidato",
                "tipo_documento": "DNI", "documento": elector.dni,
                "tipo": Candidato.Tipo.TITULAR,
                "orden": 1,
            },
        )

        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, participacion.id))}"
            f"?puesto={lista.id}&pestana_candidatos=manual#candidaturas",
        )
        self.assertTrue(Candidato.objects.filter(lista=lista, dni="30999888", elector=elector).exists())

    def test_carga_manual_rechaza_dni_ajeno_al_padron(self):
        destino = f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}?puesto={self.lista.id}"
        respuesta = self.client.post(destino, {
            "accion": "agregar_candidato", "tipo_documento": "DNI", "documento": "30999889",
            "tipo": Candidato.Tipo.TITULAR, "orden": 1,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "El documento no pertenece al padrón activo")
        self.assertFalse(Candidato.objects.filter(lista=self.lista).exists())

    def test_formulario_manual_tiene_tipo_documento_y_nombre_del_padron(self):
        destino = reverse("detalle-participacion-partido", args=(self.eleccion.id, self.participacion.id))
        respuesta = self.client.get(destino)

        self.assertEqual(list(respuesta.context["formulario_candidato"].fields), ["tipo_documento", "documento", "nombre_padron", "tipo", "orden"])
        self.assertTrue(respuesta.context["formulario_candidato"].fields["nombre_padron"].disabled)
        self.assertEqual(
            respuesta.context["formulario_candidato"].fields["orden"].help_text,
            "Define la posición del candidato dentro de la lista.",
        )
        self.assertEqual(respuesta.context["pestana_candidatos"], "manual")
        self.assertContains(respuesta, "Método de carga de candidatos")
        self.assertContains(respuesta, "Importar por CSV")
        self.assertContains(respuesta, "Agregar candidato")
        self.assertNotContains(respuesta, "Previsualizar candidatos")
        self.assertContains(respuesta, 'data-busqueda-candidato=')
        self.assertNotContains(respuesta, "DNI de elector vinculado")
        self.assertNotContains(respuesta, "Identificador de persona")

        respuesta_csv = self.client.get(
            reverse("detalle-participacion-partido", args=(self.eleccion.id, self.participacion.id)),
            {"puesto": self.lista.id, "pestana_candidatos": "csv"},
        )
        self.assertEqual(respuesta_csv.context["pestana_candidatos"], "csv")
        self.assertContains(respuesta_csv, "Importar candidatos por CSV")
        self.assertContains(respuesta_csv, "El orden indica la posición del candidato dentro de la lista.")
        self.assertNotContains(respuesta_csv, "data-busqueda-candidato=")

    def test_carga_manual_rechaza_elector_de_otro_claustro(self):
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Graduados"),
        )
        otra_configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_claustro,
            departamento=Departamento.objects.create(nombre="Civil", codigo="CIV"),
        )
        elector = self.crear_elector_padron(dni="30999890", configuracion=otra_configuracion)
        destino = f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}?puesto={self.lista.id}"
        respuesta = self.client.post(destino, {
            "accion": "agregar_candidato", "tipo_documento": "DNI", "documento": elector.dni,
            "tipo": Candidato.Tipo.TITULAR, "orden": 1,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "otro claustro")
        self.assertFalse(Candidato.objects.filter(lista=self.lista).exists())

    def test_csv_de_lista_existente_previsualiza_y_confirma_sin_crear_otra_lista(self):
        elector = self.crear_elector_padron(dni="30777777")
        plantilla = self.client.get(
            f"{reverse('plantilla-candidatos-lista', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={self.lista.id}"
        )
        self.assertEqual(plantilla.status_code, 200)
        contenido_plantilla = plantilla.content.decode("utf-8-sig")
        self.assertTrue(contenido_plantilla.startswith("tipo_documento;documento;tipo_candidatura;orden"))
        self.assertIn("DNI;;titular;1", contenido_plantilla)
        self.assertNotIn("organo", contenido_plantilla)
        self.assertNotIn("puesto", contenido_plantilla)
        self.assertNotIn("departamento", contenido_plantilla)
        self.assertNotIn("identificador_persona", plantilla.content.decode("utf-8-sig"))

        contenido = "\n".join((
            "tipo_documento;documento;tipo_candidatura;orden",
            f"DNI;{elector.dni};titular;1",
            "DNI;;suplente;1",
        ))
        archivo = SimpleUploadedFile("candidatos-lista.csv", contenido.encode("utf-8"), content_type="text/csv")
        destino = (
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={self.lista.id}&pestana_candidatos=csv"
        )
        respuesta = self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["pestana_candidatos"], "csv")
        self.assertContains(respuesta, "Importar candidatos por CSV")
        self.assertContains(respuesta, "Confirmar carga de candidatos")
        self.assertNotContains(respuesta, "data-busqueda-candidato=")
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="candidatos-lista.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertEqual(importacion.cantidad_total, 1)
        self.assertContains(respuesta, "Confirmar carga de candidatos")

        otra_lista = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="EST-OTRA",
            eleccion_claustro=self.eleccion_claustro, numero_lista="22", nombre_lista="Otra lista",
        )
        respuesta_otra_lista = self.client.post(
            reverse('detalle-participacion-partido', args=(self.eleccion.id, otra_lista.id)),
            {"accion": "confirmar_candidatos", "importacion_id": importacion.id},
        )
        self.assertEqual(respuesta_otra_lista.status_code, 404)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(Candidato.objects.filter(lista=self.lista, elector=elector).exists())

        respuesta = self.client.post(destino, {"accion": "confirmar_candidatos", "importacion_id": importacion.id})
        self.assertRedirects(
            respuesta,
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={self.lista.id}&pestana_candidatos=csv#candidaturas",
        )
        self.assertTrue(Candidato.objects.filter(lista=self.lista, elector=elector).exists())
        self.assertEqual(ParticipacionPartido.objects.filter(eleccion=self.eleccion).count(), 2)

        self.client.post(destino, {"accion": "confirmar_candidatos", "importacion_id": importacion.id})
        self.assertEqual(Candidato.objects.filter(lista=self.lista, elector=elector).count(), 1)

    def test_csv_de_lista_rechaza_puesto_no_vinculado(self):
        contenido = "\n".join((
            "organo;puesto;departamento;dni;tipo_candidatura;orden",
            "Consejo Departamental;Consejero/a;Otro;30777888;titular;1",
        ))
        archivo = SimpleUploadedFile("puesto-ajeno.csv", contenido.encode("utf-8"), content_type="text/csv")
        destino = reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))

        respuesta = self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="puesto-ajeno.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertTrue(any("no coinciden con el puesto seleccionado" in error for error in importacion.errores))
        self.assertFalse(Candidato.objects.filter(lista=self.lista).exists())

    def test_csv_de_lista_rechaza_metadatos_que_no_coinciden_con_el_puesto_seleccionado(self):
        contenido = "\n".join((
            "organo;puesto;departamento;dni;tipo_candidatura;orden",
            "Consejo Departamental;Consejero/a;Otro;30777888;titular;1",
        ))
        archivo = SimpleUploadedFile("puesto-incompatible.csv", contenido.encode("utf-8"), content_type="text/csv")
        destino = (
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={self.lista.id}&pestana_candidatos=csv"
        )

        self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})

        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="puesto-incompatible.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertTrue(any("no coinciden con el puesto seleccionado" in error for error in importacion.errores))

    def test_csv_nuevo_usa_el_puesto_seleccionado_sin_repetir_su_configuracion(self):
        cargo = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante general",
            permite_filtrar_departamentos=False,
        )
        puesto = PuestoEleccion.objects.create(
            puesto=cargo,
            eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1,
            cantidad_suplentes=1,
        )
        lista = ListaCandidatos.objects.create(
            participacion=self.participacion,
            eleccion_claustro=self.eleccion_claustro,
            nombre=str(cargo),
            puesto_eleccion=puesto,
        )
        elector = self.crear_elector_padron(dni="30999893")
        archivo = SimpleUploadedFile(
            "candidatos-puesto.csv",
            f"tipo_documento;documento;tipo_candidatura;orden\nDNI;{elector.dni};titular;1".encode("utf-8"),
            content_type="text/csv",
        )
        destino = (
            f"{reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))}"
            f"?puesto={lista.id}&pestana_candidatos=csv"
        )

        respuesta = self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="candidatos-puesto.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertEqual(importacion.filas[0]["lista_id"], lista.pk)
        self.assertEqual(importacion.filas[0]["puesto_eleccion_id"], puesto.pk)

    def test_csv_de_lista_rechaza_dni_fuera_del_padron(self):
        contenido = "\n".join((
            "organo;puesto;departamento;dni;tipo_candidatura;orden",
            "Consejo Departamental;Consejero/a;Sistemas;30999891;titular;1",
        ))
        archivo = SimpleUploadedFile("fuera-padron.csv", contenido.encode("utf-8"), content_type="text/csv")
        destino = reverse("detalle-participacion-partido", args=(self.eleccion.id, self.participacion.id))

        respuesta = self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="fuera-padron.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertTrue(any("padrón activo" in error for error in importacion.errores))

    def test_csv_no_confirma_si_elector_sale_del_padron_tras_previsualizar(self):
        elector = self.crear_elector_padron(dni="30999892")
        contenido = "\n".join((
            "organo;puesto;departamento;dni;tipo_candidatura;orden",
            f"Consejo Departamental;Consejero/a;Sistemas;{elector.dni};titular;1",
        ))
        archivo = SimpleUploadedFile("padron-cambiado.csv", contenido.encode("utf-8"), content_type="text/csv")
        destino = reverse("detalle-participacion-partido", args=(self.eleccion.id, self.participacion.id))
        self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="padron-cambiado.csv")
        RegistroPadron.objects.filter(elector=elector, eleccion=self.eleccion).update(activo=False)

        respuesta = self.client.post(destino, {"accion": "confirmar_candidatos", "importacion_id": importacion.id})

        self.assertEqual(respuesta.status_code, 302)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(Candidato.objects.filter(elector=elector).exists())


class PartidosEleccionCerradaTests(PartidosBaseTests):
    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_superuser(
            username="admin-partidos-cerrada",
            email="admin-partidos-cerrada@example.invalid",
        )
        self.client.force_login(self.usuario)

    def test_eleccion_cerrada_bloquea_las_pantallas_de_configuracion_de_candidaturas(self):
        self.eleccion.estado = Eleccion.Estado.FINALIZADA
        self.eleccion.save(update_fields=("estado",))

        rutas = (
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            reverse("detalle-participacion-partido", args=(self.eleccion.pk, self.participacion.pk)),
            reverse("editar-participacion-partido", args=(self.eleccion.pk, self.participacion.pk)),
            reverse("editar-puesto-eleccion", args=(self.eleccion.pk, self.puesto_eleccion.pk)),
            reverse("importar-candidaturas", args=(self.eleccion.pk,)),
        )

        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_csv_de_lista_no_reemplaza_un_candidato_cargado_despues_de_previsualizar(self):
        self.crear_elector_padron(dni="30777999")
        contenido = "\n".join((
            "organo;puesto;departamento;dni;tipo_candidatura;orden",
            "Consejo Departamental;Consejero/a;Sistemas;30777999;titular;1",
        ))
        archivo = SimpleUploadedFile("puesto-ocupado.csv", contenido.encode("utf-8"), content_type="text/csv")
        destino = reverse('detalle-participacion-partido', args=(self.eleccion.id, self.participacion.id))
        self.client.post(destino, {"accion": "previsualizar_candidatos", "archivo": archivo})
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="puesto-ocupado.csv")
        Candidato.objects.create(
            lista=self.lista, nombre="Candidata previa", dni="30999000", cargo="Consejero/a",
            tipo=Candidato.Tipo.TITULAR, orden=1,
        )

        respuesta = self.client.post(destino, {"accion": "confirmar_candidatos", "importacion_id": importacion.id})

        self.assertEqual(respuesta.status_code, 302)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertEqual(list(Candidato.objects.filter(lista=self.lista).values_list("nombre", flat=True)), ["Candidata previa"])

    def test_puesto_sin_alcance_departamental_rechaza_departamento(self):
        puesto_general = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante general",
            permite_filtrar_departamentos=False,
        )
        formulario = FormularioPuestoEleccion(
            data={
                "puesto": puesto_general.pk,
                "tipo_alcance": FormularioPuestoEleccion.TIPO_DEPARTAMENTO,
                "eleccion_claustro": self.eleccion_claustro.pk,
                "eleccion_claustro_departamento": self.configuracion.pk,
                "cantidad_titulares": 1,
                "cantidad_suplentes": 1,
                "activo": "on",
            },
            eleccion=self.eleccion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("eleccion_claustro_departamento", formulario.errors)

    def test_habilita_multiples_claustros_y_departamentos_en_una_operacion(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        claustro_graduado = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Graduados"),
        )
        departamento_docente = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_docente,
            departamento=Departamento.objects.create(nombre="Industrial", codigo="IND"),
        )
        departamento_graduado = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_graduado,
            departamento=Departamento.objects.create(nombre="Electrónica", codigo="ELE"),
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": self.puesto.pk,
                "puesto-limitar_por_claustros": "on",
                "puesto-claustros": [claustro_docente.pk, claustro_graduado.pk],
                "puesto-limitar_por_departamentos": "on",
                "puesto-departamentos": [
                    departamento_docente.departamento_id,
                    departamento_graduado.departamento_id,
                ],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("gestionar-partidos", args=(self.eleccion.pk,)))
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(claustro_docente, claustro_graduado),
                eleccion_claustro_departamento__isnull=False,
            ).count(),
            2,
        )
        self.assertFalse(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(claustro_docente, claustro_graduado),
                eleccion_claustro_departamento__isnull=True,
            ).exists()
        )

    def test_sin_limite_departamental_crea_un_alcance_por_cada_claustro(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        claustro_nodocente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="No Docentes"),
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": self.puesto.pk,
                "puesto-limitar_por_claustros": "on",
                "puesto-claustros": [claustro_docente.pk, claustro_nodocente.pk],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(claustro_docente, claustro_nodocente),
                eleccion_claustro_departamento__isnull=True,
            ).count(),
            2,
        )

    def test_sin_filtros_habilita_todos_los_claustros(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": self.puesto.pk,
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=self.puesto,
                eleccion_claustro__in=(self.eleccion_claustro, claustro_docente),
                eleccion_claustro_departamento__isnull=True,
            ).count(),
            2,
        )

    def test_puesto_cargado_desde_un_claustro_se_asocia_solo_a_ese_claustro(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        puesto_general = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante general",
            permite_filtrar_claustros=True,
        )

        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.pk,))}"
            f"?claustro={self.eleccion_claustro.pk}&pestana=puesto",
            {
                "accion": "configurar_puesto",
                "puesto-puesto": puesto_general.pk,
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        configuraciones = PuestoEleccion.objects.filter(puesto=puesto_general)
        self.assertEqual(configuraciones.count(), 1)
        self.assertEqual(configuraciones.get().eleccion_claustro, self.eleccion_claustro)
        self.assertNotEqual(configuraciones.get().eleccion_claustro, claustro_docente)

    def test_puesto_no_acepta_un_claustro_distinto_al_contexto_de_carga(self):
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        puesto_general = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante general",
            permite_filtrar_claustros=True,
        )

        respuesta = self.client.post(
            f"{reverse('gestionar-partidos', args=(self.eleccion.pk,))}"
            f"?claustro={self.eleccion_claustro.pk}&pestana=puesto",
            {
                "accion": "configurar_puesto",
                "puesto-puesto": puesto_general.pk,
                "puesto-limitar_por_claustros": "on",
                "puesto-claustros": [claustro_docente.pk],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("claustros", respuesta.context["formulario_puesto"].errors)
        self.assertFalse(PuestoEleccion.objects.filter(puesto=puesto_general).exists())

    def test_filtro_departamental_no_exige_activar_filtro_por_claustros(self):
        puesto_departamental = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Representante departamental",
            permite_filtrar_claustros=False,
            permite_filtrar_departamentos=True,
        )
        claustro_docente = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Docentes"),
        )
        EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_docente,
            departamento=self.configuracion.departamento,
        )

        respuesta = self.client.post(
            reverse("gestionar-partidos", args=(self.eleccion.pk,)),
            {
                "accion": "configurar_puesto",
                "puesto-puesto": puesto_departamental.pk,
                "puesto-limitar_por_departamentos": "on",
                "puesto-departamentos": [self.configuracion.departamento_id],
                "puesto-cantidad_titulares": 1,
                "puesto-cantidad_suplentes": 1,
                "puesto-activo": "on",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            PuestoEleccion.objects.filter(
                puesto=puesto_departamental,
                eleccion_claustro_departamento__departamento=self.configuracion.departamento,
            ).count(),
            2,
        )

    def test_csv_previsualiza_advierte_y_confirma_presentaciones_independientes(self):
        elector = self.crear_elector_padron(dni="30777111")
        contenido = "\n".join(
            (
                "codigo_presentacion;numero_lista;nombre_lista;apoderado_nombre;apoderado_email;claustro;organo;puesto;departamento;dni;tipo_candidatura;orden",
                f"EST-A;3;Integracion;Ana Apoderada;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;{elector.dni};titular;1",
                f"EST-B;3;Otra Integracion;Bruno Apoderado;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;{elector.dni};titular;1",
            )
        )
        archivo = SimpleUploadedFile("candidaturas.csv", contenido.encode("utf-8"), content_type="text/csv")

        respuesta = self.client.post(
            reverse("importar-candidaturas", args=(self.eleccion.pk,)),
            {"archivo": archivo},
        )

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="candidaturas.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertEqual(importacion.cantidad_valida, 2)
        self.assertEqual(len(importacion.advertencias), 1)
        self.assertContains(respuesta, "requiere revisi")

        respuesta = self.client.post(
            reverse("confirmar-importacion-candidaturas", args=(self.eleccion.pk, importacion.pk)),
        )

        self.assertEqual(respuesta.status_code, 302)
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.CONFIRMADA)
        self.assertEqual(
            ParticipacionPartido.objects.filter(eleccion=self.eleccion, numero_lista="3").count(),
            2,
        )
        self.assertEqual(Candidato.objects.filter(elector=elector).count(), 2)

    def test_csv_rechaza_orden_superior_a_la_cantidad_configurada(self):
        elector = self.crear_elector_padron(dni="30777909")
        contenido = "\n".join(
            (
                "codigo_presentacion;numero_lista;nombre_lista;apoderado_nombre;apoderado_email;claustro;organo;puesto;departamento;dni;tipo_candidatura;orden",
                f"EST-A;3;Integracion;Ana Apoderada;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;{elector.dni};titular;4",
            )
        )
        archivo = SimpleUploadedFile("orden-invalido.csv", contenido.encode("utf-8"), content_type="text/csv")

        respuesta = self.client.post(
            reverse("importar-candidaturas", args=(self.eleccion.pk,)),
            {"archivo": archivo},
        )

        self.assertEqual(respuesta.status_code, 200)
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="orden-invalido.csv")
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.RECHAZADA)
        self.assertEqual(importacion.cantidad_valida, 0)
        self.assertTrue(any("supera" in error for error in importacion.errores))

    def test_csv_general_no_confirma_si_elector_sale_del_padron(self):
        elector = self.crear_elector_padron(dni="30777910")
        contenido = "\n".join((
            "codigo_presentacion;numero_lista;nombre_lista;apoderado_nombre;apoderado_email;claustro;organo;puesto;departamento;dni;tipo_candidatura;orden",
            f"EST-A;3;Integracion;Ana Apoderada;;Estudiantes;Consejo Departamental;Consejero/a;Sistemas;{elector.dni};titular;1",
        ))
        archivo = SimpleUploadedFile("padron-general.csv", contenido.encode("utf-8"), content_type="text/csv")
        self.client.post(reverse("importar-candidaturas", args=(self.eleccion.pk,)), {"archivo": archivo})
        importacion = ImportacionCandidaturas.objects.get(nombre_archivo="padron-general.csv")
        RegistroPadron.objects.filter(elector=elector, eleccion=self.eleccion).update(activo=False)

        respuesta = self.client.post(
            reverse("confirmar-importacion-candidaturas", args=(self.eleccion.pk, importacion.pk)),
        )

        self.assertRedirects(respuesta, reverse("importar-candidaturas", args=(self.eleccion.pk,)))
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, ImportacionCandidaturas.Estado.PREVISUALIZADA)
        self.assertFalse(Candidato.objects.filter(elector=elector).exists())
