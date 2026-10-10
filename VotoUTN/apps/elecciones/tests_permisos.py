from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    FechaAdministrativaEleccion,
)
from apps.mesas.models import Mesa
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import puede_crear_elecciones, puede_importar_padron, puede_registrar_participacion, puede_revisar_justificativo


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

    def test_nav_muestra_gestionar_elecciones_al_administrador_de_junta(self):
        respuesta = self.client.get(reverse("gestionar-elecciones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, f'href="{reverse("gestionar-elecciones")}"')
        self.assertContains(respuesta, ">Gestionar elecciones</a>")

    def test_deshabilita_nueva_eleccion_y_muestra_el_estado_en_curso(self):
        for estado, etiqueta in (
            (Eleccion.Estado.BORRADOR, "Borrador"),
            (Eleccion.Estado.PREPARADA, "Preparada"),
            (Eleccion.Estado.ABIERTA, "Abierta"),
        ):
            with self.subTest(estado=estado):
                self.eleccion_asignada.estado = estado
                self.eleccion_asignada.save(update_fields=("estado",))

                respuesta = self.client.get(reverse("gestionar-elecciones"))

                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "option-disabled")
                self.assertContains(
                    respuesta,
                    f'<span class="button-tooltip__message" id="tooltip-nueva-eleccion" role="tooltip">Ya hay una elección en curso en estado: {etiqueta}</span>',
                )
                self.assertContains(respuesta, 'tabindex="0" aria-describedby="tooltip-nueva-eleccion"')
                self.assertNotContains(respuesta, f'href="{reverse("crear-eleccion")}"')

    def test_habilita_nueva_eleccion_si_no_hay_eleccion_en_curso(self):
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))

        respuesta = self.client.get(reverse("gestionar-elecciones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, f'href="{reverse("crear-eleccion")}"')
        self.assertNotContains(respuesta, "option-disabled")

    def test_listados_separan_elecciones_cerradas_de_las_gestionables(self):
        fecha = timezone.localdate()
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
        Eleccion.objects.create(
            nombre="Eleccion preparada",
            fecha_inicio=fecha,
            fecha_fin=fecha + timedelta(days=1),
            estado=Eleccion.Estado.PREPARADA,
        )
        Eleccion.objects.create(
            nombre="Eleccion cerrada",
            fecha_inicio=fecha,
            fecha_fin=fecha + timedelta(days=1),
            estado=Eleccion.Estado.CERRADA,
        )

        respuesta_gestion = self.client.get(reverse("gestionar-elecciones"))
        respuesta_historial = self.client.get(reverse("historial-elecciones"))

        self.assertEqual(respuesta_gestion.status_code, 200)
        self.assertEqual(respuesta_historial.status_code, 200)
        self.assertSetEqual(
            set(respuesta_gestion.context["elecciones"].values_list("nombre", flat=True)),
            {"Eleccion preparada"},
        )
        self.assertSetEqual(
            set(respuesta_historial.context["elecciones"].values_list("nombre", flat=True)),
            {"Eleccion asignada", "Eleccion cerrada"},
        )

    def test_administrador_junta_puede_editar_eleccion_creada_por_otro(self):
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
        otro_administrador = get_user_model().objects.create_user(username="otro-administrador")
        eleccion_ajena = Eleccion.objects.create(
            nombre="Eleccion de otro administrador",
            fecha_inicio=timezone.localdate(),
            fecha_fin=timezone.localdate() + timedelta(days=1),
        )
        AsignacionRol.objects.create(
            usuario=otro_administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=eleccion_ajena,
        )
        url = reverse("editar-eleccion", args=(eleccion_ajena.pk,))

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        nueva_fecha_inicio = timezone.localdate() + timedelta(days=10)
        nueva_fecha_fin = nueva_fecha_inicio + timedelta(days=2)
        respuesta = self.client.post(
            url,
            {
                "nombre": "Eleccion actualizada por otro administrador",
                "fecha_inicio": nueva_fecha_inicio.isoformat(),
                "fecha_fin": nueva_fecha_fin.isoformat(),
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("gestionar-elecciones"),
            fetch_redirect_response=False,
        )
        eleccion_ajena.refresh_from_db()
        self.assertEqual(eleccion_ajena.nombre, "Eleccion actualizada por otro administrador")

    def test_administrativo_junta_no_puede_editar_eleccion_ajena(self):
        AsignacionRol.objects.filter(usuario=self.usuario).delete()
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=self.eleccion_asignada,
        )
        eleccion_ajena = Eleccion.objects.create(
            nombre="Eleccion fuera de alcance",
            fecha_inicio=timezone.localdate(),
            fecha_fin=timezone.localdate() + timedelta(days=1),
        )

        respuesta = self.client.get(reverse("editar-eleccion", args=(eleccion_ajena.pk,)))

        self.assertEqual(respuesta.status_code, 403)

    def test_administrativo_sin_eleccion_asignada_puede_hacer_sus_tareas_en_todas(self):
        AsignacionRol.objects.filter(usuario=self.usuario).delete()
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
        asignacion = AsignacionRol(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=None,
        )
        asignacion.full_clean()
        asignacion.save()
        otra_eleccion = Eleccion.objects.create(
            nombre="Eleccion para todas las tareas administrativas",
            fecha_inicio=timezone.localdate(),
            fecha_fin=timezone.localdate() + timedelta(days=1),
        )

        self.assertTrue(puede_registrar_participacion(self.usuario, otra_eleccion))
        self.assertFalse(puede_importar_padron(self.usuario, otra_eleccion))
        self.assertTrue(puede_revisar_justificativo(self.usuario, otra_eleccion))
        self.assertFalse(puede_crear_elecciones(self.usuario))
        respuesta = self.client.get(reverse("inicio-administrativo-junta"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, f'href="{reverse("gestionar-elecciones")}"')

    def test_puede_abrir_el_formulario_de_nueva_eleccion(self):
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
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

    def test_no_muestra_formulario_si_ya_hay_eleccion_borrador_o_preparada(self):
        url = reverse("crear-eleccion")

        for estado in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA):
            with self.subTest(estado=estado):
                self.eleccion_asignada.estado = estado
                self.eleccion_asignada.save(update_fields=("estado",))

                respuesta = self.client.get(url)

                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Ya existe una elección creada")
                self.assertContains(respuesta, self.eleccion_asignada.nombre)
                self.assertContains(respuesta, "Ir a la elección existente")
                self.assertNotContains(respuesta, 'name="fecha_inicio"')

    def test_al_crear_eleccion_queda_asignado_como_administrador(self):
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
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
        self.assertContains(respuesta, 'class="toolbar configuration-grid"')
        self.assertContains(respuesta, 'class="option"', count=8)
        self.assertContains(respuesta, 'class="button secondary"', count=8)
        self.assertContains(
            respuesta,
            reverse("gestionar-fechas-administrativas", args=(self.eleccion_asignada.pk,)),
        )
        self.assertNotContains(respuesta, "Guardar fechas administrativas")

    def test_las_secciones_principales_vuelven_a_la_configuracion(self):
        rutas = (
            reverse("editar-eleccion", args=(self.eleccion_asignada.pk,)),
            reverse("gestionar-alcances", args=(self.eleccion_asignada.pk,)),
            reverse("preparar-eleccion", args=(self.eleccion_asignada.pk,)),
            reverse("gestionar-fechas-administrativas", args=(self.eleccion_asignada.pk,)),
        )
        destino = reverse("configurar-eleccion", args=(self.eleccion_asignada.pk,))

        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, destino)
                self.assertContains(respuesta, "Volver a configuración", count=1)
                self.assertNotContains(respuesta, "← Volver a configuración")

    def test_los_formularios_alinean_guardar_antes_de_volver(self):
        casos = (
            (
                reverse("editar-eleccion", args=(self.eleccion_asignada.pk,)),
                'form="formulario-datos-generales"',
                "Guardar cambios",
            ),
            (
                reverse("gestionar-fechas-administrativas", args=(self.eleccion_asignada.pk,)),
                'form="formulario-fechas-administrativas"',
                "Guardar fechas administrativas",
            ),
        )

        for ruta, atributo_formulario, texto_guardar in casos:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                contenido = respuesta.content.decode()
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, 'class="section-actions form-card-actions"')
                self.assertContains(respuesta, atributo_formulario)
                self.assertLess(
                    contenido.index(texto_guardar),
                    contenido.index("Volver a configuración"),
                )

    def test_nueva_eleccion_copia_la_organizacion_del_claustro(self):
        self.eleccion_asignada.estado = Eleccion.Estado.CERRADA
        self.eleccion_asignada.save(update_fields=("estado",))
        claustro_sin_departamentos = Claustro.objects.create(
            nombre="No docentes",
            abreviatura="ND",
            organizacion_departamentos=Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
            activo=True,
        )
        inicio = timezone.localdate() + timedelta(days=30)

        respuesta = self.client.post(
            reverse("crear-eleccion"),
            {
                "nombre": "Elección sin distinción departamental",
                "fecha_inicio": inicio.isoformat(),
                "fecha_fin": inicio.isoformat(),
                "sedes": [self.sede.pk],
                "claustros": [claustro_sin_departamentos.pk],
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        configuracion = EleccionClaustro.objects.get(
            eleccion__nombre="Elección sin distinción departamental",
            claustro=claustro_sin_departamentos,
        )
        self.assertEqual(
            configuracion.organizacion_departamentos,
            Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        alcance = configuracion.departamentos.get()
        self.assertIsNone(alcance.departamento)
        self.assertEqual(
            set(alcance.sedes_habilitadas.values_list("sede_id", flat=True)),
            {self.sede.pk},
        )

    def test_claustro_sin_departamentos_muestra_un_alcance_interno(self):
        EleccionSede.objects.create(eleccion=self.eleccion_asignada, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion_asignada,
            claustro=self.claustro,
            organizacion_departamentos=Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        EleccionClaustroSede.objects.create(eleccion_claustro=eleccion_claustro, sede=self.sede)
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=None,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=alcance,
            sede=self.sede,
        )

        respuesta = self.client.get(reverse("gestionar-alcances", args=(self.eleccion_asignada.pk,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Sin distinción por departamento")
        self.assertNotContains(respuesta, "Gestionar departamentos")
        self.assertContains(
            respuesta,
            reverse(
                "editar-alcance-sedes",
                args=(self.eleccion_asignada.pk, "departamento", alcance.pk),
            ),
        )

    def test_gestiona_departamentos_del_claustro_y_hereda_sus_sedes(self):
        EleccionSede.objects.create(eleccion=self.eleccion_asignada, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion_asignada,
            claustro=self.claustro,
        )
        EleccionClaustroSede.objects.create(eleccion_claustro=eleccion_claustro, sede=self.sede)
        sistemas = Departamento.objects.create(nombre="Sistemas", codigo="SIS", activo=True)
        mecanica = Departamento.objects.create(nombre="Mecánica", codigo="MEC", activo=True)
        ruta = reverse(
            "gestionar-departamentos-claustro",
            args=(self.eleccion_asignada.pk, eleccion_claustro.pk),
        )

        formulario = self.client.get(ruta)
        respuesta = self.client.post(
            ruta,
            {"departamentos": [sistemas.pk, mecanica.pk]},
        )

        self.assertContains(formulario, 'data-select-all="departamentos-claustro"')
        self.assertContains(formulario, 'form="formulario-departamentos-claustro"')
        self.assertRedirects(
            respuesta,
            reverse("gestionar-alcances", args=(self.eleccion_asignada.pk,)),
            fetch_redirect_response=False,
        )
        configuraciones = eleccion_claustro.departamentos.all()
        self.assertEqual(configuraciones.count(), 2)
        self.assertTrue(
            all(
                configuracion.sedes_habilitadas.filter(sede=self.sede).exists()
                for configuracion in configuraciones
            )
        )

    def test_no_permite_quitar_un_departamento_utilizado_por_una_mesa(self):
        EleccionSede.objects.create(eleccion=self.eleccion_asignada, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion_asignada,
            claustro=self.claustro,
        )
        EleccionClaustroSede.objects.create(eleccion_claustro=eleccion_claustro, sede=self.sede)
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="SIS", activo=True)
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=configuracion,
            sede=self.sede,
        )
        Mesa.objects.create(
            eleccion=self.eleccion_asignada,
            numero=1,
            eleccion_claustro_departamento=configuracion,
            sede=self.sede,
        )

        respuesta = self.client.post(
            reverse(
                "gestionar-departamentos-claustro",
                args=(self.eleccion_asignada.pk, eleccion_claustro.pk),
            ),
            {"departamentos": []},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pueden quitar departamentos")
        self.assertTrue(EleccionClaustroDepartamento.objects.filter(pk=configuracion.pk).exists())

    def test_sedes_y_departamentos_organiza_cada_claustro_en_una_tarjeta(self):
        EleccionSede.objects.create(eleccion=self.eleccion_asignada, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion_asignada,
            claustro=self.claustro,
        )
        EleccionClaustroSede.objects.create(eleccion_claustro=eleccion_claustro, sede=self.sede)
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="SIS", activo=True)
        alcance_departamento = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(
            eleccion_claustro_departamento=alcance_departamento,
            sede=self.sede,
        )

        respuesta = self.client.get(reverse("gestionar-alcances", args=(self.eleccion_asignada.pk,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="management-panel scopes-panel"')
        self.assertContains(respuesta, 'class="card management-section"', count=1)
        self.assertContains(respuesta, "Gestionar sedes del claustro")
        self.assertContains(respuesta, "Sistemas")
        self.assertContains(respuesta, "Gestionar sedes")

    def test_editar_sedes_alinea_guardar_y_volver_fuera_de_la_tarjeta(self):
        EleccionSede.objects.create(eleccion=self.eleccion_asignada, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion_asignada,
            claustro=self.claustro,
        )
        EleccionClaustroSede.objects.create(eleccion_claustro=eleccion_claustro, sede=self.sede)

        respuesta = self.client.get(
            reverse(
                "editar-alcance-sedes",
                args=(self.eleccion_asignada.pk, "claustro", eleccion_claustro.pk),
            )
        )
        contenido = respuesta.content.decode()

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'id="formulario-alcance-sedes"')
        self.assertContains(respuesta, 'data-select-all="alcance-sedes"')
        self.assertContains(respuesta, 'class="section-actions form-card-actions"')
        self.assertContains(respuesta, 'form="formulario-alcance-sedes"')
        self.assertLess(
            contenido.index("Guardar sedes"),
            contenido.index("Volver a sedes y departamentos"),
        )

    def test_el_periodo_puede_comenzar_y_terminar_el_mismo_dia(self):
        eleccion = Eleccion(
            nombre="Proceso de un dia",
            fecha_inicio=timezone.localdate(),
            fecha_fin=timezone.localdate(),
            estado=Eleccion.Estado.CERRADA,
        )

        eleccion.full_clean()

    def test_usuario_sin_rol_no_puede_crear_eleccion(self):
        usuario_sin_rol = get_user_model().objects.create_user(username="sin-rol")
        self.client.force_login(usuario_sin_rol)

        respuesta = self.client.get(reverse("crear-eleccion"))

        self.assertEqual(respuesta.status_code, 403)

    def test_administrativo_junta_no_puede_crear_elecciones(self):
        self.usuario.asignaciones_rol.all().delete()
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
            eleccion=self.eleccion_asignada,
        )

        self.assertFalse(puede_crear_elecciones(self.usuario))
        self.assertEqual(self.client.get(reverse("crear-eleccion")).status_code, 403)


class EleccionCerradaSoloConsultaTests(TestCase):
    def setUp(self):
        fecha = timezone.localdate()
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion cerrada de prueba",
            fecha_inicio=fecha - timedelta(days=2),
            fecha_fin=fecha - timedelta(days=1),
            estado=Eleccion.Estado.CERRADA,
            habilitada=False,
        )
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=Claustro.objects.create(nombre="Claustro cerrado de prueba"),
        )
        self.usuario = get_user_model().objects.create_user(username="admin-eleccion-cerrada")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(self.usuario)

    def test_pantallas_de_configuracion_de_eleccion_cerrada_estan_bloqueadas(self):
        rutas = (
            reverse("configurar-eleccion", args=(self.eleccion.pk,)),
            reverse("editar-eleccion", args=(self.eleccion.pk,)),
            reverse("gestionar-fechas-administrativas", args=(self.eleccion.pk,)),
            reverse("preparar-eleccion", args=(self.eleccion.pk,)),
            reverse("preparar-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk)),
            reverse("gestionar-alcances", args=(self.eleccion.pk,)),
            reverse("gestionar-departamentos-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk)),
            reverse("editar-alcance-sedes", args=(self.eleccion.pk, "claustro", self.eleccion_claustro.pk)),
        )

        for ruta in rutas:
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_eleccion_cerrada_rechaza_edicion_y_cambio_de_estado_por_post(self):
        respuesta_edicion = self.client.post(
            reverse("editar-eleccion", args=(self.eleccion.pk,)),
            {
                "nombre": "Nombre alterado",
                "fecha_inicio": self.eleccion.fecha_inicio.isoformat(),
                "fecha_fin": self.eleccion.fecha_fin.isoformat(),
            },
        )
        respuesta_estado = self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)),
            {"estado": Eleccion.Estado.ABIERTA},
        )

        self.assertEqual(respuesta_edicion.status_code, 403)
        self.assertEqual(respuesta_estado.status_code, 403)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.nombre, "Eleccion cerrada de prueba")
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.CERRADA)

    def test_historial_sigue_consultable_y_dashboard_permanece_pendiente(self):
        respuesta = self.client.get(reverse("historial-elecciones"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, f'href="{reverse("historial-elecciones")}?eleccion={self.eleccion.pk}">Dashboard</a>')
        self.assertNotContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.pk,)))
