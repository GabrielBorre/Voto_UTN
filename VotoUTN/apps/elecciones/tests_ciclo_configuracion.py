from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionClaustroTurno, EleccionSede,
)
from apps.elecciones.services import agregar_claustro, eliminar_claustro
from apps.mesas.models import AsignacionMesa, Mesa
from apps.notificaciones.models import EnvioNotificacion
from apps.notificaciones.services import notificar_eleccion_en_curso
from apps.padron.models import ConfiguracionSedesClaustro, Elector, RegistroPadron, SolicitudCambioSede
from apps.padron.services import (
    estimar_mesas_adicionales_por_sede, registrar_emision_padron_imprimible,
    resolver_solicitud_cambio_sede, resolver_solicitudes_pendientes,
)
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.usuarios.models import AsignacionRol, PerfilUsuario
from apps.usuarios.permisos import puede_configurar_eleccion


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CicloConfiguracionTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="junta-global")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA)
        self.client.force_login(self.usuario)
        hoy = timezone.localdate()
        self.eleccion = Eleccion.objects.create(
            nombre="Elección actual", fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=5),
        )
        self.sedes = [Sede.objects.create(nombre=nombre) for nombre in ("Campus", "Medrano")]
        for sede in self.sedes:
            EleccionSede.objects.create(eleccion=self.eleccion, sede=sede)
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.configuracion = agregar_claustro(self.eleccion, self.claustro)
        self.configuracion.maximo_votantes_por_mesa = 1
        self.configuracion.fecha_votacion = hoy
        self.configuracion.save()
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        self.alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.configuracion, departamento=self.departamento,
        )
        for sede in self.sedes:
            EleccionClaustroDepartamentoSede.objects.create(
                eleccion_claustro_departamento=self.alcance, sede=sede,
            )
        self.turno = Turno.objects.create(nombre="Mañana", hora_inicio="08:00", hora_fin="12:00")
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.configuracion, turno=self.turno)
        ConfiguracionSedesClaustro.objects.create(eleccion_claustro=self.configuracion)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=1, sede=self.sedes[0],
            eleccion_claustro_departamento=self.alcance,
        )
        self.registro = self.crear_registro("40100001")
        AsignacionMesa.objects.create(registro_padron=self.registro, mesa=self.mesa)

    def crear_registro(self, dni):
        elector = Elector.objects.create(
            dni=dni, legajo=dni, nombre="Ana", apellido="Prueba", correo_electronico="elector@example.test",
        )
        return RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.alcance, sede=self.sedes[0],
        )

    def estado(self, estado):
        self.eleccion.estado = estado
        self.eleccion.save(update_fields=("estado",))

    def solicitud(self, registro=None):
        return SolicitudCambioSede.objects.create(
            registro_padron=registro or self.registro, sede_origen=self.sedes[0], sede_destino=self.sedes[1],
        )

    def test_configuracion_en_curso_es_consultable_pero_post_bloqueado(self):
        self.estado(Eleccion.Estado.ABIERTA)
        rutas = [
            ("editar-eleccion", (self.eleccion.pk,)),
            ("gestionar-alcances", (self.eleccion.pk,)),
            ("gestionar-departamentos-claustro", (self.eleccion.pk, self.configuracion.pk)),
            ("editar-alcance-sedes", (self.eleccion.pk, "claustro", self.configuracion.pk)),
            ("previsualizar-padron", (self.eleccion.pk, self.configuracion.pk)),
            ("configurar-sedes-claustro", (self.eleccion.pk, self.configuracion.pk)),
            ("gestionar-autoridades", (self.eleccion.pk,)),
            ("gestionar-autoridades-claustro", (self.eleccion.pk, self.configuracion.pk)),
            ("gestionar-partidos", (self.eleccion.pk,)),
        ]
        self.assertFalse(puede_configurar_eleccion(self.usuario, self.eleccion))
        self.assertTrue(puede_configurar_eleccion(self.usuario, self.eleccion, solo_consulta=True))
        for nombre, argumentos in rutas:
            with self.subTest(ruta=nombre):
                url = reverse(nombre, args=argumentos)
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["configuracion_solo_lectura"])
                self.assertContains(respuesta, "disabled")
                self.assertEqual(self.client.post(url, {"nombre": "No cambiar"}).status_code, 403)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.nombre, "Elección actual")

    def test_fechas_y_cambio_de_estado_siguen_habilitados_en_curso(self):
        self.estado(Eleccion.Estado.ABIERTA)
        url = reverse("gestionar-fechas-administrativas", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["configuracion_solo_lectura"])
        self.assertEqual(self.client.post(url, {}).status_code, 302)
        self.mesa.estado_escaneo = Mesa.EstadoEscaneo.PROCESADA
        self.mesa.save(update_fields=("estado_escaneo",))
        self.assertEqual(self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {"estado": Eleccion.Estado.CERRADA},
        ).status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.CERRADA)

    def test_transicion_bloqueada_se_informa_como_popup(self):
        self.estado(Eleccion.Estado.ABIERTA)
        respuesta = self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)),
            {"estado": Eleccion.Estado.CERRADA}, follow=True,
        )
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.ABIERTA)
        self.assertContains(respuesta, "data-popup-mensaje")
        self.assertContains(respuesta, 'data-popup-titulo="No se puede cambiar el estado"')
        self.assertContains(respuesta, "No se puede finalizar la elección con mesas pendientes de escaneo.")

    def test_claustro_nuevo_hereda_sedes_y_se_elimina_sin_borrar_padrones(self):
        otro = Claustro.objects.create(
            nombre="No docentes", organizacion_departamentos=Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO,
        )
        url = reverse("gestionar-alcances", args=(self.eleccion.pk,))
        self.assertEqual(self.client.post(url, {"accion": "agregar_claustro", "claustro": otro.pk}).status_code, 302)
        configuracion = EleccionClaustro.objects.get(eleccion=self.eleccion, claustro=otro)
        self.assertEqual(configuracion.sedes_habilitadas.count(), 2)
        self.assertEqual(configuracion.departamentos.get().sedes_habilitadas.count(), 2)
        self.assertEqual(self.client.post(url, {
            "accion": "eliminar_claustro", "claustro_id": configuracion.pk,
        }).status_code, 302)
        self.assertFalse(EleccionClaustro.objects.filter(eleccion=self.eleccion, claustro=otro).exists())
        self.assertEqual(RegistroPadron.objects.count(), 1)

    def test_claustro_con_padron_no_se_elimina_y_se_restauran_sedes(self):
        with self.assertRaisesMessage(ValueError, "datos vinculados"):
            eliminar_claustro(self.configuracion, self.usuario)
        self.assertEqual(self.configuracion.sedes_habilitadas.count(), 2)
        self.assertEqual(self.alcance.sedes_habilitadas.count(), 2)
        self.assertTrue(RegistroPadron.objects.filter(pk=self.registro.pk).exists())

    def test_agregar_y_eliminar_claustros_solo_en_preparacion(self):
        otro = Claustro.objects.create(nombre="Docentes")
        for estado in (Eleccion.Estado.PREPARADA, Eleccion.Estado.ABIERTA, Eleccion.Estado.CERRADA):
            with self.subTest(estado=estado):
                self.estado(estado)
                with self.assertRaisesMessage(ValueError, "En preparación"):
                    agregar_claustro(self.eleccion, otro)
                with self.assertRaisesMessage(ValueError, "En preparación"):
                    eliminar_claustro(self.configuracion, self.usuario)
                self.assertEqual(self.client.post(reverse("gestionar-alcances", args=(self.eleccion.pk,)), {
                    "accion": "agregar_claustro", "claustro": otro.pk,
                }).status_code, 403)

    def test_seleccion_estima_y_aprueba_solo_las_solicitudes_marcadas(self):
        self.estado(Eleccion.Estado.ABIERTA)
        seleccionada = self.solicitud()
        no_seleccionada = self.solicitud(self.crear_registro("40100002"))
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        respuesta = self.client.get(url, {"accion": "estimar_seleccion", "solicitudes_ids": [seleccionada.pk]})
        self.assertEqual(respuesta.json(), {
            "mesas_por_sede": {str(self.sedes[1].pk): 1}, "total": 1, "seleccionadas": 1,
        })
        self.assertEqual(self.client.post(url, {
            "accion": "aprobar_seleccionadas", "solicitudes_ids": [seleccionada.pk],
        }).status_code, 302)
        seleccionada.refresh_from_db()
        no_seleccionada.refresh_from_db()
        self.assertEqual(seleccionada.estado, SolicitudCambioSede.Estado.APROBADA)
        self.assertEqual(no_seleccionada.estado, SolicitudCambioSede.Estado.PENDIENTE)
        self.assertEqual(EnvioNotificacion.objects.count(), 1)

    def test_seleccion_invalida_o_vacia_no_resuelve_ninguna_solicitud(self):
        self.estado(Eleccion.Estado.PREPARADA)
        solicitud = self.solicitud()
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        for ids in ([], [solicitud.pk, solicitud.pk + 10000], ["invalido"]):
            with self.subTest(ids=ids):
                self.assertEqual(self.client.post(url, {
                    "accion": "aprobar_seleccionadas", "solicitudes_ids": ids,
                }).status_code, 302)
                solicitud.refresh_from_db()
                self.assertEqual(solicitud.estado, SolicitudCambioSede.Estado.PENDIENTE)
                self.assertEqual(Mesa.objects.count(), 1)
        self.assertEqual(self.client.get(url, {
            "accion": "estimar_seleccion", "solicitudes_ids": ["no-es-id"],
        }).status_code, 400)
        self.assertEqual(self.client.get(url, {
            "accion": "estimar_seleccion", "solicitudes_ids": [solicitud.pk + 10000],
        }).status_code, 400)

    def test_emision_bloquea_todas_las_resoluciones_y_preserva_qr(self):
        self.estado(Eleccion.Estado.ABIERTA)
        solicitud = self.solicitud(self.crear_registro("40100003"))
        registrar_emision_padron_imprimible(self.eleccion, self.usuario)
        self.registro.refresh_from_db()
        identificador = self.registro.identificador_qr
        for estado in (SolicitudCambioSede.Estado.APROBADA, SolicitudCambioSede.Estado.RECHAZADA):
            with self.assertRaisesMessage(ValueError, "modo lectura"):
                resolver_solicitud_cambio_sede(solicitud, estado, self.usuario)
        for accion in ("aprobar_todas", "rechazar_todas", "aprobar_sin_agregar_mesas", "aprobar_con_maximo_mesas"):
            with self.assertRaisesMessage(ValueError, "modo lectura"):
                resolver_solicitudes_pendientes(self.eleccion, usuario=self.usuario, accion=accion)
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)
        self.assertTrue(respuesta.context["solo_lectura"])
        self.assertContains(respuesta, '<fieldset class="configuracion-campos" disabled>', html=False)
        self.assertEqual(self.client.post(url, {"accion": "rechazar_todas"}).status_code, 403)
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.identificador_qr, identificador)
        self.assertEqual(self.client.post(reverse(
            "rehabilitar-cambios-padron", args=(self.eleccion.pk, self.configuracion.pk),
        )).status_code, 403)

    def test_estimacion_simula_movimientos_sucesivos_y_coincide_con_mesas_creadas(self):
        self.estado(Eleccion.Estado.PREPARADA)
        segundo = self.crear_registro("40100004")
        mesa_destino = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sedes[1],
            eleccion_claustro_departamento=self.alcance,
        )
        AsignacionMesa.objects.create(registro_padron=segundo, mesa=mesa_destino)
        self.solicitud()
        SolicitudCambioSede.objects.create(
            registro_padron=segundo, sede_origen=self.sedes[1], sede_destino=self.sedes[0],
        )
        consulta = SolicitudCambioSede.objects.all()
        impacto = estimar_mesas_adicionales_por_sede(self.eleccion, consulta)
        self.assertEqual(impacto, {self.sedes[1].pk: 1})
        previas = Mesa.objects.count()
        resolver_solicitudes_pendientes(self.eleccion, usuario=self.usuario, accion="aprobar_todas")
        self.assertEqual(Mesa.objects.count() - previas, sum(impacto.values()))

    def test_inicio_admin_global_muestra_cuatro_cards_sin_acciones(self):
        respuesta = self.client.get(reverse("inicio-administrador-junta"))
        for titulo in ("Elección actual", "Justificativos pendientes", "Solicitudes de cambio de sede pendientes", "Participación"):
            self.assertContains(respuesta, titulo)
        self.assertContains(respuesta, '<article class="option">', count=4)
        self.assertNotContains(respuesta, "Revisar solicitudes")
        self.assertNotContains(respuesta, '<a class="button')
        self.eleccion.estado = Eleccion.Estado.CERRADA
        self.eleccion.save(update_fields=("estado",))
        self.assertContains(self.client.get(reverse("inicio-administrador-junta")), "Crear elección")

    def test_codigo_departamento_mesa_en_mail_y_cards_elector_y_autoridad(self):
        self.estado(Eleccion.Estado.ABIERTA)
        with patch("apps.notificaciones.services.enviar_notificacion"):
            notificar_eleccion_en_curso(self.eleccion)
        self.assertIn("K-001", EnvioNotificacion.objects.get().contenido)
        PerfilUsuario.objects.create(usuario=self.usuario, elector=self.registro.elector)
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ELECTOR)
        AsignacionAutoridad.objects.create(
            registro_padron=self.registro, mesa=self.mesa, turno=self.turno, asignada_por=self.usuario,
        )
        respuesta = self.client.get(reverse("inicio-autenticado"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "K-001", count=2)

    def test_admin_django_no_permite_modificar_la_configuracion_en_curso(self):
        peticion = RequestFactory().post("/")
        self.usuario.is_superuser = True
        peticion.user = self.usuario
        administrador = admin.site._registry[EleccionClaustro]
        self.assertTrue(administrador.has_change_permission(peticion, self.configuracion))
        self.estado(Eleccion.Estado.ABIERTA)
        self.configuracion.eleccion = self.eleccion
        self.assertFalse(administrador.has_change_permission(peticion, self.configuracion))
        self.assertFalse(administrador.has_delete_permission(peticion, self.configuracion))
        with self.assertRaises(PermissionDenied):
            administrador.save_model(peticion, self.configuracion, None, True)
        with self.assertRaises(PermissionDenied):
            administrador.delete_model(peticion, self.configuracion)

    def test_participacion_del_inicio_solo_cuenta_votos_confirmados_en_mesas_procesadas(self):
        self.estado(Eleccion.Estado.ABIERTA)
        segundo = self.crear_registro("40100005")
        AsignacionMesa.objects.create(registro_padron=segundo, mesa=self.mesa)
        self.mesa.estado_escaneo = Mesa.EstadoEscaneo.PROCESADA
        self.mesa.save(update_fields=("estado_escaneo",))
        RegistroParticipacion.objects.create(
            registro_padron=segundo, mesa=self.mesa, registrada_por=self.usuario,
            metodo=RegistroParticipacion.Metodo.QR,
        )
        dashboard = self.client.get(reverse("inicio-administrador-junta")).context["dashboard"]
        self.assertEqual(dashboard["electores_participaron"], 1)
        self.assertEqual(dashboard["electores_participaron_pct"], 50)
        self.mesa.estado_escaneo = Mesa.EstadoEscaneo.PENDIENTE
        self.mesa.save(update_fields=("estado_escaneo",))
        dashboard = self.client.get(reverse("inicio-administrador-junta")).context["dashboard"]
        self.assertEqual(dashboard["electores_participaron"], 0)
        self.assertEqual(dashboard["electores_participaron_pct"], 0)
