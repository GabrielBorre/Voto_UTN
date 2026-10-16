from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.test import override_settings
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
                correo_electronico="juan@example.test",
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
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.CERRADA)
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
                "ausencia": JustificativoAusencia.Ausencia.VOTAR,
                "tipo": tipo.id,
                "detalle": "Ausencia por enfermedad.",
            },
        )

        self.assertRedirects(respuesta, reverse("mis-justificativos"))
        justificativo = JustificativoAusencia.objects.get(registro_padron__elector=registro_reciente.elector)
        self.assertEqual(justificativo.registro_padron, registro_reciente)

    def test_elector_solo_puede_presentar_un_justificativo_de_votar(self):
        usuario, _, registro_reciente = self.crear_elector_con_padrones()
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        datos = {"ausencia": "votar", "tipo": tipo.id, "detalle": "Detalle."}
        self.client.login(username=usuario.username, password="clave")

        self.client.post(reverse("mis-justificativos"), datos)
        respuesta = self.client.post(reverse("mis-justificativos"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(JustificativoAusencia.objects.filter(registro_padron=registro_reciente).count(), 1)

    def test_autoridad_puede_presentar_un_justificativo_por_tipo_de_ausencia(self):
        from apps.autoridades.models import AsignacionAutoridad
        from apps.mesas.models import Mesa
        from apps.parametros.models import Sede, Turno

        usuario, _, registro = self.crear_elector_con_padrones()
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        sede = Sede.objects.create(nombre="Central")
        turno = Turno.objects.create(nombre="Mañana", hora_inicio="08:00", hora_fin="12:00")
        mesa = Mesa.objects.create(
            eleccion=registro.eleccion,
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            sede=sede,
            numero=1,
        )
        AsignacionAutoridad.objects.bulk_create([
            AsignacionAutoridad(registro_padron=registro, mesa=mesa, turno=turno, asignada_por=usuario)
        ])
        self.client.login(username=usuario.username, password="clave")

        for ausencia in ("votar", "autoridad", "autoridad"):
            self.client.post(reverse("mis-justificativos"), {"ausencia": ausencia, "tipo": tipo.id, "detalle": "x"})

        self.assertEqual(JustificativoAusencia.objects.filter(registro_padron=registro).count(), 2)

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

    def test_justificativo_de_eleccion_en_historial_solo_se_puede_consultar(self):
        justificativo = self.crear_justificativo()
        justificativo.estado = JustificativoAusencia.Estado.APROBADO
        justificativo.observacion_resolucion = "Resolución histórica conservada."
        justificativo.resuelta_por = self.usuario
        justificativo.resuelta_en = make_aware(datetime(2026, 8, 4, 10))
        justificativo.save()
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.CERRADA)
        self.client.login(username="admin", ******)
        url = reverse("resolver-justificativo", args=(justificativo.id,))

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Elección en el historial")
        self.assertContains(respuesta, "Resolución histórica conservada.")
        self.assertNotContains(respuesta, 'id="formulario-resolucion-justificativo"')
        self.assertNotContains(respuesta, "Guardar resolución")

        respuesta = self.client.post(
            url,
            {
                "estado": JustificativoAusencia.Estado.RECHAZADO,
                "observacion_resolucion": "Intento de modificación.",
            },
        )

        self.assertEqual(respuesta.status_code, 403)
        justificativo.refresh_from_db()
        self.assertEqual(justificativo.estado, JustificativoAusencia.Estado.APROBADO)
        self.assertEqual(justificativo.observacion_resolucion, "Resolución histórica conservada.")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_resolver_justificativo_envia_correo_al_elector_una_sola_vez(self):
        justificativo = self.crear_justificativo()
        self.client.login(username="admin", password="clave")
        url = reverse("resolver-justificativo", args=(justificativo.id,))
        datos = {
            "estado": JustificativoAusencia.Estado.APROBADO,
            "observacion_resolucion": "Documentación validada.",
        }

        respuesta = self.client.post(url, datos)
        self.client.post(url, datos)

        self.assertRedirects(respuesta, reverse("gestionar-justificativos", args=(self.eleccion.id,)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["juan@example.test"])
        self.assertIn("fue aprobado", mail.outbox[0].body)
        self.assertIn("Documentación validada.", mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_administrador_junta_envia_correo_al_resolver_justificativo(self):
        justificativo = self.crear_justificativo()
        administrador = get_user_model().objects.create_user(username="administrador", password="clave")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.login(username=administrador.username, password="clave")

        respuesta = self.client.post(
            reverse("resolver-justificativo", args=(justificativo.id,)),
            {
                "estado": JustificativoAusencia.Estado.RECHAZADO,
                "observacion_resolucion": "Documentación insuficiente.",
            },
        )

        self.assertRedirects(respuesta, reverse("gestionar-justificativos", args=(self.eleccion.id,)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["juan@example.test"])
        self.assertIn("fue rechazado", mail.outbox[0].body)

    def test_gestionar_justificativos_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-justificativos", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "justificativos/gestion.html")
        self.assertContains(respuesta, 'class="management-panel justifications-panel"')
        self.assertContains(respuesta, "Solicitudes recibidas")
        self.assertContains(respuesta, "Inasistencia de electores")
        self.assertContains(respuesta, "Inasistencia de autoridades de mesa")
        self.assertNotContains(respuesta, "Volver a configuración")

    def test_pestana_autoridades_solo_lista_ausencias_de_autoridad(self):
        self.client.login(username="admin", password="clave")
        self.crear_justificativo()

        respuesta = self.client.get(
            reverse("gestionar-justificativos", args=(self.eleccion.id,)), {"pestana": "autoridades"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["justificativos"]), 0)

    def test_filtro_de_estado_limita_los_justificativos_listados(self):
        self.client.login(username="admin", password="clave")
        self.crear_justificativo()
        url = reverse("gestionar-justificativos", args=(self.eleccion.id,))

        pendientes = self.client.get(url, {"estado": "pendiente"})
        aprobados = self.client.get(url, {"estado": "aprobado"})

        self.assertEqual(len(pendientes.context["justificativos"]), 1)
        self.assertEqual(len(aprobados.context["justificativos"]), 0)
