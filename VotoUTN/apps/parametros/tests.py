from datetime import date
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import TestCase
from django.urls import reverse
from io import StringIO

from apps.auditoria.models import EventoAuditoria
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.justificativos.models import TipoJustificativo
from apps.notificaciones.models import ComunicacionFechaAdministrativa, PlantillaNotificacion
from apps.parametros.forms import FormularioFechaAdministrativa
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno
from apps.partidos.forms import FormularioCargoElectivo
from apps.partidos.models import (
    Candidato, CargoElectivo, CupoPuestoClaustro, ListaCandidatos, NOMBRE_PUESTO_CIENCIAS_BASICAS,
    OrganoElectivo, ParticipacionPartido, PuestoEleccion,
)


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

    def test_formulario_de_claustro_expone_abreviatura_y_organizacion(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("crear-parametro", args=("claustros",)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Abreviatura")
        self.assertContains(respuesta, "Organización del claustro")
        self.assertContains(respuesta, "Por departamentos")
        self.assertContains(respuesta, "Sin distinción por departamento")

    def test_panel_incluye_los_siete_catalogos_y_puestos_a_elegir(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-parametros"))

        self.assertEqual(len(respuesta.context["parametros"]), 8)
        self.assertContains(respuesta, "Plantillas de mensajes")
        self.assertContains(respuesta, "Puestos a elegir")
        self.assertContains(
            respuesta,
            f'href="{reverse("listar-parametros", args=("puestos-electivos",))}"',
        )
        self.assertNotContains(respuesta, "Agrupaciones y cargos a elegir")

    def test_puestos_estandar_se_muestran_con_sus_nuevos_nombres(self):
        call_command("cargar_parametros_estandar", stdout=StringIO())
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("listar-parametros", args=("puestos-electivos",)))

        self.assertContains(respuesta, "Consejero/a Superior")
        self.assertContains(respuesta, "Consejero/a Ciencias Básicas")

    def test_tabla_de_ciencias_basicas_muestra_cupo_departamental_de_docentes(self):
        call_command("cargar_parametros_estandar", stdout=StringIO())
        self.client.force_login(self.usuario)
        generales = CargoElectivo.objects.get(nombre=NOMBRE_PUESTO_CIENCIAS_BASICAS)
        departamental = CargoElectivo.objects.get(nombre="Consejero/a departamental")
        cupo = departamental.cupos_claustro.get(claustro__nombre="Docentes")
        cupo.cantidad_titulares = 7
        cupo.save(update_fields=("cantidad_titulares",))

        respuesta = self.client.get(reverse("listar-parametros", args=("puestos-electivos",)))

        self.assertContains(respuesta, "Docentes: 7 tit. / 5 sup. (departamental Z)")
        self.assertFalse(generales.claustros_habilitados.filter(nombre="Docentes").exists())
        departamental.claustros_habilitados.remove(cupo.claustro)
        respuesta = self.client.get(reverse("listar-parametros", args=("puestos-electivos",)))
        self.assertNotContains(respuesta, "(departamental Z)")

    def test_alta_y_cambio_de_estado_quedan_auditados(self):
        self.client.login(username="admin", password="clave")
        self.client.post(reverse("crear-parametro", args=("sedes",)), {"nombre": "Medrano", "activa": "on"})
        sede = Sede.objects.get(nombre="Medrano")
        self.client.post(reverse("cambiar-estado-parametro", args=("sedes", sede.pk)))

        self.assertEqual(EventoAuditoria.objects.filter(entidad="parametros.Sede").count(), 2)
        sede.refresh_from_db()
        self.assertFalse(sede.activa)


class CatalogosEstandarTests(TestCase):
    def test_migracion_actualiza_solo_cupos_solicitados_y_eleccion_en_preparacion(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        cargo = CargoElectivo.objects.create(organo=organo, nombre="Consejero/a directivo/a")
        graduados = Claustro.objects.create(nombre="Graduados")
        no_docentes = Claustro.objects.create(nombre="No docentes")
        docentes = Claustro.objects.create(nombre="Docentes")
        cargo.claustros_habilitados.add(graduados, no_docentes, docentes)
        for claustro, titulares, suplentes in ((graduados, 10, 1), (no_docentes, 2, 1), (docentes, 1, 1)):
            CupoPuestoClaustro.objects.create(
                puesto=cargo, claustro=claustro, cantidad_titulares=titulares, cantidad_suplentes=suplentes,
            )
        preparacion = Eleccion.objects.create(nombre="Preparación", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 1))
        finalizada = Eleccion.objects.create(
            nombre="Finalizada", fecha_inicio=date(2026, 10, 1), fecha_fin=date(2026, 10, 1),
            estado=Eleccion.Estado.FINALIZADA,
        )
        ec_grad = EleccionClaustro.objects.create(eleccion=preparacion, claustro=graduados)
        ec_nd = EleccionClaustro.objects.create(eleccion=preparacion, claustro=no_docentes)
        ec_final = EleccionClaustro.objects.create(eleccion=finalizada, claustro=graduados)
        puesto = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=ec_grad, cantidad_titulares=10, cantidad_suplentes=1,
        )
        historico = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=ec_final, cantidad_titulares=10, cantidad_suplentes=1,
        )

        migracion = import_module("apps.partidos.migrations.0017_actualizar_cupos_estandar")
        migracion.actualizar_cupos(apps, SimpleNamespace(connection=connection))

        cupo_graduados = cargo.cupos_claustro.get(claustro=graduados)
        self.assertEqual((cupo_graduados.cantidad_titulares, cupo_graduados.cantidad_suplentes), (5, 5))
        self.assertEqual(
            list(cargo.cupos_claustro.filter(claustro=docentes).values_list("cantidad_titulares", "cantidad_suplentes")),
            [(1, 1)],
        )
        puesto.refresh_from_db()
        historico.refresh_from_db()
        self.assertEqual((puesto.cantidad_titulares, puesto.cantidad_suplentes), (5, 5))
        self.assertEqual((historico.cantidad_titulares, historico.cantidad_suplentes), (10, 1))
        nuevo = PuestoEleccion.objects.get(puesto=cargo, eleccion_claustro=ec_nd)
        self.assertEqual((nuevo.cantidad_titulares, nuevo.cantidad_suplentes), (1, 1))

    def test_migracion_rechaza_reduccion_que_afecta_candidaturas(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        cargo = CargoElectivo.objects.create(organo=organo, nombre="Consejero/a directivo/a")
        graduados = Claustro.objects.create(nombre="Graduados")
        cargo.claustros_habilitados.add(graduados)
        cupo = CupoPuestoClaustro.objects.create(
            puesto=cargo, claustro=graduados, cantidad_titulares=10, cantidad_suplentes=1,
        )
        eleccion = Eleccion.objects.create(nombre="Preparación", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 1))
        ec = EleccionClaustro.objects.create(eleccion=eleccion, claustro=graduados)
        puesto = PuestoEleccion.objects.create(puesto=cargo, eleccion_claustro=ec, cantidad_titulares=10, cantidad_suplentes=1)
        participacion = ParticipacionPartido.objects.create(
            eleccion=eleccion, eleccion_claustro=ec, numero_lista="1", codigo_presentacion="TEST",
        )
        lista = ListaCandidatos.objects.create(participacion=participacion, eleccion_claustro=ec, puesto_eleccion=puesto)
        Candidato.objects.create(lista=lista, nombre="Candidata", cargo="Consejera", tipo="titular", orden=6)

        migracion = import_module("apps.partidos.migrations.0017_actualizar_cupos_estandar")
        with self.assertRaisesMessage(RuntimeError, "candidaturas titular fuera del nuevo cupo"):
            with transaction.atomic():
                migracion.actualizar_cupos(apps, SimpleNamespace(connection=connection))
        cupo.refresh_from_db()
        puesto.refresh_from_db()
        self.assertEqual((cupo.cantidad_titulares, cupo.cantidad_suplentes), (10, 1))
        self.assertEqual((puesto.cantidad_titulares, puesto.cantidad_suplentes), (10, 1))
        self.assertEqual(Candidato.objects.filter(lista=lista).count(), 1)

    def test_semilla_reutiliza_puesto_superior_anterior(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Superior")
        puesto = CargoElectivo.objects.create(organo=organo, nombre="Consejo Superior")
        call_command("cargar_parametros_estandar", stdout=StringIO())
        puesto.refresh_from_db()
        self.assertEqual(puesto.nombre, "Consejero/a Superior")
        self.assertEqual(CargoElectivo.objects.filter(organo=organo).count(), 1)

    def test_migracion_renombra_sin_cambiar_puestos_ni_cupos(self):
        superior = OrganoElectivo.objects.create(nombre="Consejo Superior")
        ciencias = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        puesto_superior = CargoElectivo.objects.create(organo=superior, nombre="Consejo Superior")
        puesto_ciencias = CargoElectivo.objects.create(organo=ciencias, nombre="Ciencias Basicas")
        claustro = Claustro.objects.create(nombre="Estudiantes")
        puesto_ciencias.claustros_habilitados.add(claustro)
        cupo = CupoPuestoClaustro.objects.create(
            puesto=puesto_ciencias, claustro=claustro, cantidad_titulares=3, cantidad_suplentes=3,
        )

        migracion = import_module("apps.partidos.migrations.0016_renombrar_puestos_estandar")
        migracion.renombrar_puestos(apps, SimpleNamespace(connection=connection))
        puesto_superior.refresh_from_db()
        puesto_ciencias.refresh_from_db()
        cupo.refresh_from_db()
        self.assertEqual(puesto_superior.nombre, "Consejero/a Superior")
        self.assertEqual(puesto_ciencias.nombre, NOMBRE_PUESTO_CIENCIAS_BASICAS)
        self.assertEqual(cupo.puesto_id, puesto_ciencias.pk)
        self.assertTrue(puesto_ciencias.claustros_habilitados.filter(pk=claustro.pk).exists())

    def test_migracion_rechaza_puestos_equivalentes_sin_fusionar(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Superior")
        anterior = CargoElectivo.objects.create(organo=organo, nombre="Consejo Superior")
        nuevo = CargoElectivo.objects.create(organo=organo, nombre="Consejero/a Superior")
        migracion = import_module("apps.partidos.migrations.0016_renombrar_puestos_estandar")

        with self.assertRaisesMessage(RuntimeError, "varios puestos equivalentes"):
            migracion.renombrar_puestos(apps, SimpleNamespace(connection=connection))
        self.assertEqual(CargoElectivo.objects.filter(pk__in=(anterior.pk, nuevo.pk)).count(), 2)

    def test_semilla_reutiliza_ciencias_actual_y_conserva_cupos_editados(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        puesto = CargoElectivo.objects.create(organo=organo, nombre="Ciencias Basicas")
        estudiantes = Claustro.objects.create(nombre="Estudiantes")
        puesto.claustros_habilitados.add(estudiantes)
        CupoPuestoClaustro.objects.create(
            puesto=puesto, claustro=estudiantes, cantidad_titulares=4, cantidad_suplentes=3,
        )

        call_command("cargar_parametros_estandar", stdout=StringIO())

        self.assertEqual(CargoElectivo.objects.get(organo=organo, nombre=NOMBRE_PUESTO_CIENCIAS_BASICAS).pk, puesto.pk)
        self.assertFalse(CargoElectivo.objects.filter(organo=organo, nombre="Ciencias Basicas").exists())
        cupo = puesto.cupos_claustro.get(claustro=estudiantes)
        self.assertEqual((cupo.cantidad_titulares, cupo.cantidad_suplentes), (4, 3))

    def test_semilla_reutiliza_nombre_historico_y_conserva_departamento(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        departamento = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        anterior = CargoElectivo.objects.create(
            organo=organo, nombre="Consejero/a departamental de Ciencias Básicas",
            permite_filtrar_departamentos=True, departamento=departamento,
        )

        call_command("cargar_parametros_estandar", stdout=StringIO())

        anterior.refresh_from_db()
        self.assertEqual(anterior.nombre, NOMBRE_PUESTO_CIENCIAS_BASICAS)
        self.assertFalse(anterior.es_departamental)
        self.assertEqual(anterior.departamento_id, departamento.pk)
        self.assertFalse(CargoElectivo.objects.filter(organo=organo, nombre="Ciencias Basicas").exists())
        self.assertEqual(
            set(anterior.claustros_habilitados.values_list("nombre", flat=True)),
            {"Estudiantes", "Graduados"},
        )

    def test_semilla_rechaza_dos_puestos_de_ciencias_sin_modificarlos(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        anterior = CargoElectivo.objects.create(
            organo=organo, nombre=NOMBRE_PUESTO_CIENCIAS_BASICAS, permite_filtrar_departamentos=True,
        )
        CargoElectivo.objects.create(organo=organo, nombre="Ciencias Basicas")

        with self.assertRaisesMessage(CommandError, "varios puestos equivalentes"):
            call_command("cargar_parametros_estandar", stdout=StringIO())

        anterior.refresh_from_db()
        self.assertTrue(anterior.es_departamental)
        self.assertEqual(CargoElectivo.objects.count(), 2)

    def test_semilla_no_reemplaza_puestos_departamentales_de_eleccion_en_preparacion(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        departamento = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        cargo = CargoElectivo.objects.create(
            organo=organo, nombre=NOMBRE_PUESTO_CIENCIAS_BASICAS,
            permite_filtrar_departamentos=True, departamento=departamento,
        )
        claustro = Claustro.objects.create(nombre="Estudiantes")
        cargo.claustros_habilitados.add(claustro)
        eleccion = Eleccion.objects.create(
            nombre="Preparación", fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 1),
        )
        ec = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro)
        alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=ec, departamento=departamento)
        puesto = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=ec, eleccion_claustro_departamento=alcance,
            cantidad_titulares=3, cantidad_suplentes=3,
        )

        with self.assertRaisesMessage(CommandError, "alcances departamentales"):
            call_command("cargar_parametros_estandar", stdout=StringIO())

        cargo.refresh_from_db()
        self.assertTrue(cargo.es_departamental)
        self.assertTrue(PuestoEleccion.objects.filter(pk=puesto.pk).exists())

    def test_carga_exacta_es_idempotente_reactiva_y_no_elimina_personalizados(self):
        salida = StringIO()
        call_command("cargar_parametros_estandar", stdout=salida)

        self.assertEqual(Sede.objects.filter(nombre__in=("Medrano", "Campus")).count(), 2)
        self.assertEqual(Claustro.objects.count(), 4)
        no_docentes = Claustro.objects.get(nombre="No docentes")
        self.assertEqual(no_docentes.abreviatura, "ND")
        self.assertEqual(
            no_docentes.organizacion_departamentos,
            Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        self.assertEqual(
            Claustro.objects.get(nombre="Docentes").organizacion_departamentos,
            Claustro.OrganizacionDepartamentos.POR_DEPARTAMENTO,
        )
        self.assertEqual(Turno.objects.count(), 3)
        self.assertEqual(Departamento.objects.count(), 10)
        self.assertEqual(FechaAdministrativa.objects.count(), 3)
        self.assertFalse(FechaAdministrativa.objects.filter(
            codigo__in=(
                "exhibicion-padron-provisorio",
                "publicacion-padron-definitivo",
                "justificacion-ausencia-electoral",
            ),
        ).exists())
        self.assertEqual(PlantillaNotificacion.objects.count(), 26)
        self.assertEqual(OrganoElectivo.objects.count(), 4)
        consejo_superior = OrganoElectivo.objects.get(nombre="Consejo Superior", activo=True)
        formulario_puesto = FormularioCargoElectivo()
        self.assertIn(consejo_superior, formulario_puesto.fields["organo"].queryset)
        self.assertEqual(CargoElectivo.objects.count(), 5)
        claustros_por_puesto = {
            ("Consejo Superior", "Consejero/a Superior"): {"Docentes", "Estudiantes", "Graduados", "No docentes"},
            ("Consejo Directivo", "Consejero/a directivo/a"): {"Docentes", "Estudiantes", "Graduados", "No docentes"},
            ("Consejo Departamental", "Consejero/a departamental"): {"Docentes", "Estudiantes", "Graduados"},
            ("Consejo Departamental", NOMBRE_PUESTO_CIENCIAS_BASICAS): {"Estudiantes", "Graduados"},
            ("Consejo DASUTeN", "Consejero/a DASUTeN"): {"Docentes", "No docentes"},
        }
        for (organo, nombre), esperados in claustros_por_puesto.items():
            puesto = CargoElectivo.objects.get(organo__nombre=organo, nombre=nombre)
            self.assertEqual(set(puesto.claustros_habilitados.values_list("nombre", flat=True)), esperados)
        for organo, claustro, esperado in (
            ("Consejo Superior", "Docentes", (15, 15)),
            ("Consejo Superior", "Graduados", (5, 5)),
            ("Consejo Superior", "No docentes", (5, 5)),
            ("Consejo Directivo", "Graduados", (5, 5)),
            ("Consejo Directivo", "No docentes", (1, 1)),
            ("Consejo DASUTeN", "Docentes", (2, 2)),
            ("Consejo DASUTeN", "No docentes", (2, 2)),
        ):
            cupo = CupoPuestoClaustro.objects.get(puesto__organo__nombre=organo, claustro__nombre=claustro)
            self.assertEqual((cupo.cantidad_titulares, cupo.cantidad_suplentes), esperado)
        puesto_ciencias_basicas = CargoElectivo.objects.get(nombre=NOMBRE_PUESTO_CIENCIAS_BASICAS)
        self.assertFalse(puesto_ciencias_basicas.es_departamental)
        self.assertIsNone(puesto_ciencias_basicas.departamento)
        cupos_ciencias_basicas = {
            cupo.claustro.nombre: (cupo.cantidad_titulares, cupo.cantidad_suplentes)
            for cupo in puesto_ciencias_basicas.cupos_claustro.select_related("claustro")
        }
        self.assertEqual(cupos_ciencias_basicas, {"Estudiantes": (3, 3), "Graduados": (2, 2)})
        self.assertEqual(TipoJustificativo.objects.count(), 0)
        puesto_departamental = CargoElectivo.objects.get(
            organo__nombre="Consejo Departamental",
            nombre="Consejero/a departamental",
        )
        self.assertTrue(puesto_departamental.es_departamental)
        self.assertIsNone(puesto_departamental.departamento)
        self.assertFalse(
            CargoElectivo.objects.get(nombre="Consejero/a Superior").es_departamental
        )
        cupo_editado = puesto_departamental.cupos_claustro.get(claustro__nombre="Docentes")
        cupo_editado.cantidad_titulares = 7
        cupo_editado.save(update_fields=("cantidad_titulares",))
        plantilla = PlantillaNotificacion.objects.get(codigo="padron-definitivo-publicado")
        plantilla.activa = False
        plantilla.save(update_fields=("activa",))
        extra = Sede.objects.create(nombre="Sede personalizada", activa=False)
        ids = {codigo: pk for codigo, pk in PlantillaNotificacion.objects.values_list("codigo", "pk")}

        call_command("cargar_parametros_estandar", stdout=StringIO())

        self.assertEqual(PlantillaNotificacion.objects.count(), 26)
        self.assertEqual(OrganoElectivo.objects.count(), 4)
        self.assertEqual(CargoElectivo.objects.count(), 5)
        for (organo, nombre), esperados in claustros_por_puesto.items():
            puesto = CargoElectivo.objects.get(organo__nombre=organo, nombre=nombre)
            self.assertEqual(set(puesto.claustros_habilitados.values_list("nombre", flat=True)), esperados)
        self.assertEqual(ids, {codigo: pk for codigo, pk in PlantillaNotificacion.objects.values_list("codigo", "pk")})
        self.assertEqual(puesto_departamental.cupos_claustro.get(claustro__nombre="Docentes").cantidad_titulares, 7)
        plantilla.refresh_from_db()
        self.assertTrue(plantilla.activa)
        self.assertTrue(Sede.objects.filter(pk=extra.pk).exists())

    def test_carga_estandar_no_reactiva_fechas_ni_comunicaciones_retiradas(self):
        fecha = FechaAdministrativa.objects.create(
            codigo="exhibicion-padron-provisorio",
            nombre="Exhibición del padrón provisorio",
            activa=False,
        )
        comunicacion = ComunicacionFechaAdministrativa.objects.create(
            fecha_administrativa=fecha,
            codigo="apertura",
            nombre="Apertura",
            activa=False,
        )

        call_command("cargar_parametros_estandar", stdout=StringIO())

        fecha.refresh_from_db()
        comunicacion.refresh_from_db()
        self.assertFalse(fecha.activa)
        self.assertFalse(comunicacion.activa)

        fecha_justificativos = FechaAdministrativa.objects.create(
            codigo="justificacion-ausencia-electoral",
            nombre="Justificación ausencia electoral",
            activa=False,
        )
        comunicacion_justificativos = ComunicacionFechaAdministrativa.objects.create(
            fecha_administrativa=fecha_justificativos,
            codigo="apertura",
            nombre="Apertura de justificativos",
            activa=False,
        )

        call_command("cargar_parametros_estandar", stdout=StringIO())

        fecha_justificativos.refresh_from_db()
        comunicacion_justificativos.refresh_from_db()
        self.assertFalse(fecha_justificativos.activa)
        self.assertFalse(comunicacion_justificativos.activa)


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
        self.assertContains(
            respuesta,
            '<a class="active" href="/gestion/parametros/">Parámetros Generales</a>',
        )
        self.assertNotContains(respuesta, "Agrupaciones")
        self.assertNotContains(respuesta, "Órganos o cuerpos")
        self.assertContains(respuesta, "Puestos a elegir")
        self.assertEqual(len(respuesta.context["catalogos"]), 1)
        self.assertEqual(respuesta.context["catalogos"][0]["tipo"], "puestos-electivos")

    def test_se_crea_puesto_y_el_estado_se_audita(self):
        organo = OrganoElectivo.objects.create(nombre="DASUTeN")
        respuesta = self.client.post(reverse("crear-parametro", args=("puestos-electivos",)), {
            "organo": organo.pk, "nombre": "Representante", "tipo_alcance": "departamental",
            "descripcion": "", "activo": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        cargo = CargoElectivo.objects.get(organo=organo, nombre="Representante")
        self.assertTrue(cargo.es_departamental)
        self.client.post(reverse("cambiar-estado-parametro", args=("puestos-electivos", cargo.pk)))
        cargo.refresh_from_db()
        self.assertFalse(cargo.activo)
        self.assertEqual(EventoAuditoria.objects.filter(entidad="partidos.CargoElectivo").count(), 2)

    def test_editar_puesto_define_claustros_cantidades_y_alcance(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        puesto = CargoElectivo.objects.create(organo=organo, nombre="Consejero/a")
        docentes, estudiantes = (Claustro.objects.create(nombre=nombre) for nombre in ("Docentes", "Estudiantes"))
        destino = reverse("editar-parametro", args=("puestos-electivos", puesto.pk))

        formulario = self.client.get(destino)
        self.assertContains(formulario, "Departamental")
        self.assertContains(formulario, "General")
        self.assertNotContains(formulario, 'name="departamento"')
        self.assertContains(formulario, '<fieldset class="field puesto-alcance">')
        self.assertContains(formulario, 'class="puesto-alcance-radio"', count=2)
        self.assertContains(formulario, f'name="titulares_{docentes.pk}"')
        self.assertContains(formulario, f'name="suplentes_{estudiantes.pk}"')

        respuesta = self.client.post(destino, {
            "organo": organo.pk, "nombre": "Consejero/a", "tipo_alcance": "departamental", "activo": "on",
            f"claustro_{docentes.pk}": "on", f"titulares_{docentes.pk}": "5", f"suplentes_{docentes.pk}": "4",
            f"titulares_{estudiantes.pk}": "2", f"suplentes_{estudiantes.pk}": "2",
        })

        self.assertRedirects(respuesta, reverse("listar-parametros", args=("puestos-electivos",)))
        puesto.refresh_from_db()
        self.assertTrue(puesto.es_departamental)
        self.assertEqual(list(puesto.claustros_habilitados.all()), [docentes])
        cupo = puesto.cupos_claustro.get()
        self.assertEqual((cupo.claustro, cupo.cantidad_titulares, cupo.cantidad_suplentes), (docentes, 5, 4))
        listado = self.client.get(reverse("listar-parametros", args=("puestos-electivos",)))
        self.assertContains(listado, "Docentes: 5 tit. / 4 sup.")
        self.assertContains(listado, "Departamental")
        self.assertNotContains(listado, "Estudiantes: 2")
        evento = EventoAuditoria.objects.filter(accion="actualizar_parametro", entidad="partidos.CargoElectivo").get()
        self.assertIn("Docentes: 5 titulares / 4 suplentes", str(evento.datos_nuevos))

        respuesta = self.client.post(destino, {
            "organo": organo.pk, "nombre": "Consejero/a", "tipo_alcance": "general", "activo": "on",
            f"claustro_{estudiantes.pk}": "on", f"titulares_{estudiantes.pk}": "3", f"suplentes_{estudiantes.pk}": "1",
            f"titulares_{docentes.pk}": "5", f"suplentes_{docentes.pk}": "4",
        })

        self.assertEqual(respuesta.status_code, 302)
        puesto.refresh_from_db()
        self.assertFalse(puesto.es_departamental)
        self.assertEqual(list(puesto.claustros_habilitados.all()), [estudiantes])
        self.assertEqual(list(puesto.cupos_claustro.values_list("claustro__nombre", flat=True)), ["Estudiantes"])

    def test_editar_no_altera_departamento_historico(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        departamento = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        puesto = CargoElectivo.objects.create(
            organo=organo, nombre="Consejero/a", permite_filtrar_departamentos=True,
            departamento=departamento,
        )
        respuesta = self.client.post(reverse("editar-parametro", args=("puestos-electivos", puesto.pk)), {
            "organo": organo.pk, "nombre": puesto.nombre, "tipo_alcance": "departamental", "activo": "on",
        })
        self.assertEqual(respuesta.status_code, 302)
        puesto.refresh_from_db()
        self.assertEqual(puesto.departamento_id, departamento.pk)

    def test_cupos_de_claustros_asociados_exigen_titulares_y_suplentes(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        claustro = Claustro.objects.create(nombre="Docentes")

        respuesta = self.client.post(reverse("crear-parametro", args=("puestos-electivos",)), {
            "organo": organo.pk, "nombre": "Consejero/a", "tipo_alcance": "general", "activo": "on",
            f"claustro_{claustro.pk}": "on", f"titulares_{claustro.pk}": "3", f"suplentes_{claustro.pk}": "0",
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(CargoElectivo.objects.filter(nombre="Consejero/a").exists())
        self.assertIn(f"suplentes_{claustro.pk}", respuesta.context["formulario"].errors)

    def test_catalogo_de_organos_ya_no_se_ofrece_como_abm(self):
        respuesta = self.client.get(reverse("listar-parametros", args=("organos-electivos",)))

        self.assertEqual(respuesta.status_code, 404)

    def test_cargo_unico_por_organo_y_organo_inactivo_no_se_ofrece(self):
        primero = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        segundo = OrganoElectivo.objects.create(nombre="Consejo Superior")
        inactivo = OrganoElectivo.objects.create(nombre="Inactivo", activo=False)
        CargoElectivo.objects.create(organo=primero, nombre="Representante")

        duplicado = FormularioCargoElectivo(data={
            "organo": primero.pk, "nombre": "Representante", "tipo_alcance": "general", "activo": "on",
        })
        otro_organo = FormularioCargoElectivo(data={
            "organo": segundo.pk, "nombre": "Representante", "tipo_alcance": "general", "activo": "on",
        })
        formulario_nuevo = FormularioCargoElectivo()

        self.assertFalse(duplicado.is_valid())
        self.assertTrue(otro_organo.is_valid())
        self.assertNotIn(inactivo, formulario_nuevo.fields["organo"].queryset)

    def test_puesto_sin_claustros_es_valido(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        formulario = FormularioCargoElectivo(data={
            "organo": organo.pk,
            "nombre": "Representante",
            "tipo_alcance": "general",
            "activo": "on",
        })

        self.assertTrue(formulario.is_valid())

    def test_listado_permite_buscar_cargos_por_organo(self):
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        CargoElectivo.objects.create(organo=organo, nombre="Representante")

        respuesta = self.client.get(reverse("listar-parametros", args=("puestos-electivos",)), {"q": "Directivo"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Representante")
