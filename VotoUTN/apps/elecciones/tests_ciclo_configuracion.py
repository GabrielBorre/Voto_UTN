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
    FechaAdministrativaEleccion,
)
from apps.elecciones.forms import (
    FormularioEditarPlazoCambioSede,
    FormularioEditarPlazoEximicionAutoridades,
    FormularioFechasAdministrativasEleccion,
)
from apps.elecciones.services import agregar_claustro, eliminar_claustro
from apps.mesas.models import AsignacionMesa, Mesa
from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion
from apps.notificaciones.services import notificar_eleccion_en_curso
from apps.padron.models import ConfiguracionSedesClaustro, Elector, RegistroPadron, SolicitudCambioSede
from apps.padron.services import (
    estimar_impacto_mesas_por_sede, estimar_mesas_adicionales_por_sede, registrar_emision_padron_imprimible,
    resolver_solicitud_cambio_sede, resolver_solicitudes_pendientes,
)
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno
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

    def test_fechas_retiradas_no_se_muestran_y_conservan_programaciones_existentes(self):
        definiciones = [
            FechaAdministrativa.objects.create(codigo=codigo, nombre=nombre)
            for codigo, nombre in (
                ("exhibicion-padron-provisorio", "Exhibición del padrón provisorio"),
                ("justificacion-ausencia-electoral", "Justificación ausencia electoral"),
            )
        ]
        programaciones = [
            FechaAdministrativaEleccion.objects.create(
                eleccion=self.eleccion,
                fecha_administrativa=definicion,
                fecha=self.eleccion.fecha_inicio,
            )
            for definicion in definiciones
        ]
        formulario = FormularioFechasAdministrativasEleccion(data={}, eleccion=self.eleccion)

        for definicion in definiciones:
            self.assertNotIn(f"fecha_{definicion.pk}_seleccionada", formulario.fields)
        self.assertTrue(formulario.is_valid())
        formulario.guardar()

        for programacion in programaciones:
            self.assertTrue(FechaAdministrativaEleccion.objects.filter(pk=programacion.pk).exists())

    def test_publicacion_solicita_solo_plazo_de_cambio_sede(self):
        respuesta = self.client.get(reverse("configurar-eleccion", args=(self.eleccion.pk,)))
        self.assertContains(respuesta, 'id="dialogo-publicacion"')
        self.assertContains(respuesta, 'name="fecha_cierre_solicitudes_cambio_sede"')
        self.assertNotContains(respuesta, 'name="fecha_limite_justificacion_autoridades"')
        self.assertTrue(respuesta.context["formulario_publicacion"].fields["fecha_cierre_solicitudes_cambio_sede"].required)
        self.assertNotIn("fecha_limite_justificacion_autoridades", respuesta.context["formulario_publicacion"].fields)

    def test_publicacion_rechaza_plazos_omitidos_o_invalidos(self):
        url = reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,))
        for datos in (
            {},
            {"fecha_cierre_solicitudes_cambio_sede": "inválida"},
        ):
            with self.subTest(datos=datos):
                respuesta = self.client.post(url, {"estado": "publicada", **datos}, follow=True)
                self.eleccion.refresh_from_db()
                self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_PREPARACION)
                self.assertIsNone(self.eleccion.fecha_cierre_solicitudes_cambio_sede)
                self.assertContains(respuesta, "data-popup-mensaje")

    def test_estados_avanzan_con_plazos_pasados_y_futuros(self):
        url = reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,))
        self.mesa.estado_escaneo = Mesa.EstadoEscaneo.PROCESADA
        self.mesa.save(update_fields=("estado_escaneo",))
        for desplazamiento in (-30, 30):
            with self.subTest(desplazamiento=desplazamiento):
                self.estado(Eleccion.Estado.EN_PREPARACION)
                limite = timezone.localdate() + timedelta(days=desplazamiento)
                self.client.post(url, {
                    "estado": "publicada",
                    "fecha_cierre_solicitudes_cambio_sede": limite.isoformat(),
                })
                self.eleccion.refresh_from_db()
                self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)
                self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, limite)
                self.assertIsNotNone(self.eleccion.solicitudes_cambio_sede_habilitadas_en)
                self.assertEqual(
                    timezone.localdate(self.eleccion.solicitudes_cambio_sede_habilitadas_en),
                    timezone.localdate(),
                )
                self.assertIsNone(self.eleccion.fecha_limite_justificacion_autoridades)
                # La publicación no elimina las validaciones para iniciar la elección.

    def test_plazo_cambio_sede_es_editable_hasta_confirmar_autoridades(self):
        fecha_inicio_periodo = timezone.now() - timedelta(days=2)
        fecha_vencida = timezone.localdate() - timedelta(days=1)
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.solicitudes_cambio_sede_habilitadas_en = fecha_inicio_periodo
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = fecha_vencida
        self.eleccion.save(update_fields=(
            "estado",
            "solicitudes_cambio_sede_habilitadas_en",
            "fecha_cierre_solicitudes_cambio_sede",
        ))
        url = reverse("gestionar-fechas-administrativas", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)

        self.assertTrue(respuesta.context["puede_editar_plazo_cambio_sede"])
        self.assertContains(respuesta, "Solicitudes de cambio de sede")
        self.assertContains(respuesta, fecha_inicio_periodo.strftime("%d/%m/%Y"))
        self.assertContains(respuesta, 'id="abrir-dialogo-editar-plazo-cambio-sede"')
        self.assertContains(
            respuesta,
            "Se notificará a los electores que todavía no presentaron una solicitud de cambio de sede.",
        )
        self.assertContains(respuesta, "Presentar una solicitud es opcional.")

        nueva_fecha = timezone.localdate() + timedelta(days=3)
        registro_con_solicitud = self.crear_registro("40100002")
        solicitud_rechazada = self.solicitud(registro_con_solicitud)
        solicitud_rechazada.estado = SolicitudCambioSede.Estado.RECHAZADA
        solicitud_rechazada.save(update_fields=("estado",))
        registro_con_solicitud_pendiente = self.crear_registro("40100003")
        self.solicitud(registro_con_solicitud_pendiente)
        with patch("apps.elecciones.views.enviar_notificacion") as enviar:
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self.client.post(url, {
                    "accion": "actualizar_plazo_cambio_sede",
                    "fecha_cierre_solicitudes_cambio_sede": nueva_fecha.isoformat(),
                })
            enviar.assert_called_once()
        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, nueva_fecha)
        notificacion = EnvioNotificacion.objects.get(
            plantilla__codigo="elector-plazo-cambio-sede-modificado",
        )
        self.assertEqual(notificacion.elector, self.registro.elector)
        self.assertEqual(
            notificacion.contenido,
            (
                f"Hola {self.registro.elector.nombre_completo},\n\n"
                "Se extendió la fecha límite para solicitar un cambio de sede en "
                f"{self.eleccion.nombre}. Podés presentar tu solicitud hasta el "
                f"{nueva_fecha.strftime('%d/%m/%Y')} inclusive. Presentar una solicitud es opcional.\n\n"
                "Voto UTN"
            ),
        )
        self.assertEqual(
            EnvioNotificacion.objects.filter(
                plantilla__codigo="elector-plazo-cambio-sede-modificado",
            ).count(),
            1,
        )

        fecha_confirmacion = timezone.now()
        self.eleccion.autoridades_confirmadas_en = fecha_confirmacion
        self.eleccion.save(update_fields=("autoridades_confirmadas_en",))
        fecha_rechazada = nueva_fecha + timedelta(days=2)
        respuesta = self.client.post(url, {
            "accion": "actualizar_plazo_cambio_sede",
            "fecha_cierre_solicitudes_cambio_sede": fecha_rechazada.isoformat(),
        })

        self.assertEqual(respuesta.status_code, 403)
        respuesta = self.client.get(url)
        self.assertFalse(respuesta.context["puede_editar_plazo_cambio_sede"])
        self.assertNotContains(respuesta, 'id="abrir-dialogo-editar-plazo-cambio-sede"')
        self.assertContains(respuesta, "Período cerrado al confirmar las autoridades")
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, nueva_fecha)

    def test_formulario_plazo_cambio_sede_no_acepta_fin_anterior_al_inicio(self):
        self.eleccion.solicitudes_cambio_sede_habilitadas_en = timezone.now()
        formulario = FormularioEditarPlazoCambioSede(
            data={
                "fecha_cierre_solicitudes_cambio_sede": (
                    timezone.localdate() - timedelta(days=1)
                ).isoformat(),
            },
            eleccion=self.eleccion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn(
            "fecha_cierre_solicitudes_cambio_sede",
            formulario.errors,
        )

    def test_formulario_plazo_cambio_sede_solo_acepta_extensiones(self):
        fecha_limite = timezone.localdate() + timedelta(days=5)
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = fecha_limite
        self.eleccion.save(update_fields=("fecha_cierre_solicitudes_cambio_sede",))

        for nueva_fecha in (fecha_limite, fecha_limite - timedelta(days=1)):
            with self.subTest(nueva_fecha=nueva_fecha):
                formulario = FormularioEditarPlazoCambioSede(
                    data={
                        "fecha_cierre_solicitudes_cambio_sede": nueva_fecha.isoformat(),
                    },
                    eleccion=self.eleccion,
                )

                self.assertFalse(formulario.is_valid())
                self.assertIn(
                    "posterior a la fecha límite actual",
                    formulario.errors["fecha_cierre_solicitudes_cambio_sede"][0],
                )

    def test_formulario_cambio_sede_propone_el_dia_posterior_al_limite_actual(self):
        fecha_limite_actual = timezone.localdate() + timedelta(days=3)
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = fecha_limite_actual
        self.eleccion.solicitudes_cambio_sede_habilitadas_en = timezone.now() - timedelta(days=2)

        formulario = FormularioEditarPlazoCambioSede(eleccion=self.eleccion)
        fecha_sugerida = fecha_limite_actual + timedelta(days=1)

        self.assertEqual(
            formulario.fields["fecha_cierre_solicitudes_cambio_sede"].initial,
            fecha_sugerida,
        )
        self.assertEqual(
            formulario.fields["fecha_cierre_solicitudes_cambio_sede"].widget.attrs["min"],
            fecha_sugerida.isoformat(),
        )

    def test_formulario_cambio_sede_no_acepta_fecha_anterior_a_hoy(self):
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = timezone.localdate() - timedelta(days=2)
        formulario = FormularioEditarPlazoCambioSede(
            data={
                "fecha_cierre_solicitudes_cambio_sede": (
                    timezone.localdate() - timedelta(days=1)
                ).isoformat(),
            },
            eleccion=self.eleccion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn(
            "La fecha límite no puede ser anterior a hoy.",
            formulario.errors["fecha_cierre_solicitudes_cambio_sede"],
        )

    def test_plazo_eximicion_se_edita_en_publicada_y_queda_informativo_en_curso(self):
        fecha_inicio_periodo = timezone.now() - timedelta(days=2)
        fecha_limite = timezone.localdate() + timedelta(days=3)
        AsignacionAutoridad.objects.create(
            registro_padron=self.registro,
            mesa=self.mesa,
            turno=self.turno,
            asignada_por=self.usuario,
        )
        self.eleccion.estado = Eleccion.Estado.PUBLICADA
        self.eleccion.autoridades_confirmadas_en = fecha_inicio_periodo
        self.eleccion.fecha_limite_justificacion_autoridades = fecha_limite
        self.eleccion.save(update_fields=(
            "estado",
            "autoridades_confirmadas_en",
            "fecha_limite_justificacion_autoridades",
        ))
        url = reverse("gestionar-fechas-administrativas", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)

        self.assertTrue(respuesta.context["puede_editar_plazo_eximicion"])
        self.assertContains(respuesta, "Eximición de autoridades de mesa")
        self.assertContains(respuesta, fecha_inicio_periodo.strftime("%d/%m/%Y"))
        self.assertContains(respuesta, 'id="abrir-dialogo-editar-plazo-eximicion"')
        self.assertContains(respuesta, "Se notificará a las autoridades de mesa asignadas.")
        self.assertIn(
            f'value="{(fecha_limite + timedelta(days=1)).isoformat()}"',
            str(respuesta.context["formulario_plazo_eximicion"][
                "fecha_limite_justificacion_autoridades"
            ]),
        )

        nueva_fecha_limite = timezone.localdate() + timedelta(days=5)
        PlantillaNotificacion.objects.create(
            codigo="autoridad-plazo-eximicion-modificado",
            nombre="Autoridad: modificación del plazo de eximición",
            categoria=PlantillaNotificacion.Categoria.TRANSACCIONAL,
            asunto="Nueva fecha límite para justificar inasistencia: {nombre_eleccion}",
            contenido=(
                "Hola {nombre},\n\n"
                "Se actualizó la fecha límite para justificar una inasistencia como autoridad "
                f"de mesa en {self.eleccion.nombre}. Podés presentar tu justificativo hasta el "
                f"{nueva_fecha_limite.strftime('%d/%m/%Y')} inclusive.\n\nVoto UTN"
            ),
            roles_destinatarios=[AsignacionRol.Rol.AUTORIDAD_MESA],
            permite_envio_manual=False,
        )
        with patch("apps.elecciones.views.enviar_notificacion") as enviar:
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self.client.post(url, {
                    "accion": "actualizar_plazo_eximicion_autoridades",
                    "fecha_limite_justificacion_autoridades": nueva_fecha_limite.isoformat(),
                })
            enviar.assert_called_once()
        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.fecha_limite_justificacion_autoridades, nueva_fecha_limite)
        self.assertEqual(
            EnvioNotificacion.objects.filter(
                plantilla__codigo="autoridad-plazo-eximicion-modificado",
            ).count(),
            1,
        )
        notificacion = EnvioNotificacion.objects.get(
            plantilla__codigo="autoridad-plazo-eximicion-modificado",
        )
        self.assertEqual(
            notificacion.contenido,
            (
                f"Hola {self.registro.elector.nombre_completo},\n\n"
                "Se actualizó la fecha límite para solicitar ser eximido de la función de autoridad "
                f"de mesa en {self.eleccion.nombre}. Podés presentar tu justificativo hasta el "
                f"{nueva_fecha_limite.strftime('%d/%m/%Y')} inclusive.\n\nVoto UTN"
            ),
        )

        self.estado(Eleccion.Estado.EN_CURSO)
        respuesta = self.client.get(url)
        self.assertFalse(respuesta.context["puede_editar_plazo_eximicion"])
        self.assertNotContains(respuesta, 'id="abrir-dialogo-editar-plazo-eximicion"')
        self.assertContains(respuesta, "solo informativos")
        respuesta = self.client.post(url, {
            "accion": "actualizar_plazo_eximicion_autoridades",
            "fecha_limite_justificacion_autoridades": (
                nueva_fecha_limite + timedelta(days=2)
            ).isoformat(),
        })

        self.assertEqual(respuesta.status_code, 403)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.fecha_limite_justificacion_autoridades, nueva_fecha_limite)

    def test_formulario_eximicion_no_acepta_fecha_limite_anterior_a_hoy(self):
        self.eleccion.autoridades_confirmadas_en = timezone.now()
        formulario = FormularioEditarPlazoEximicionAutoridades(
            data={
                "fecha_limite_justificacion_autoridades": (
                    timezone.localdate() - timedelta(days=1)
                ).isoformat(),
            },
            eleccion=self.eleccion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn("fecha_limite_justificacion_autoridades", formulario.errors)

    def test_formulario_eximicion_sugiere_el_dia_posterior_al_limite_actual(self):
        fecha_limite_actual = timezone.localdate() + timedelta(days=3)
        self.eleccion.fecha_limite_justificacion_autoridades = fecha_limite_actual

        formulario = FormularioEditarPlazoEximicionAutoridades(eleccion=self.eleccion)

        fecha_sugerida = fecha_limite_actual + timedelta(days=1)
        self.assertEqual(
            formulario.fields["fecha_limite_justificacion_autoridades"].initial,
            fecha_sugerida,
        )
        self.assertEqual(
            formulario.fields["fecha_limite_justificacion_autoridades"].widget.attrs["min"],
            fecha_sugerida.isoformat(),
        )

    def test_formulario_eximicion_rechaza_fecha_igual_al_limite_actual(self):
        fecha_limite_actual = timezone.localdate() + timedelta(days=3)
        self.eleccion.fecha_limite_justificacion_autoridades = fecha_limite_actual
        formulario = FormularioEditarPlazoEximicionAutoridades(
            data={
                "fecha_limite_justificacion_autoridades": fecha_limite_actual.isoformat(),
            },
            eleccion=self.eleccion,
        )

        self.assertFalse(formulario.is_valid())
        self.assertIn(
            "La nueva fecha límite debe ser posterior a la fecha límite actual.",
            formulario.errors["fecha_limite_justificacion_autoridades"],
        )

    def test_publicacion_fallida_no_guarda_plazos(self):
        self.configuracion.sedes_habilitadas.all().delete()
        self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {
            "estado": "publicada",
            "fecha_cierre_solicitudes_cambio_sede": "2026-10-01",
        })
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_PREPARACION)
        self.assertIsNone(self.eleccion.fecha_cierre_solicitudes_cambio_sede)
        self.assertIsNone(self.eleccion.fecha_limite_justificacion_autoridades)

    def test_puede_publicar_sin_turnos_provisorios_y_no_muestra_advertencia(self):
        self.configuracion.turnos_autoridad.all().delete()
        respuesta = self.client.get(reverse("configurar-eleccion", args=(self.eleccion.pk,)))
        self.assertNotContains(respuesta, "configurá los turnos y asigná autoridades de mesa")
        self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {
            "estado": "publicada",
            "fecha_cierre_solicitudes_cambio_sede": (timezone.localdate() + timedelta(days=3)).isoformat(),
        })
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)

    def test_no_inicia_eleccion_sin_turnos_configurados(self):
        from django.core.exceptions import ValidationError

        self.configuracion.turnos_autoridad.all().delete()
        self.estado(Eleccion.Estado.PUBLICADA)
        with self.assertRaisesMessage(ValidationError, "configurá los turnos y asigná autoridades de mesa"):
            self.eleccion.cambiar_estado(Eleccion.Estado.EN_CURSO)

    def test_publicacion_no_define_plazo_de_eximicion_de_autoridades(self):
        limite = timezone.localdate() + timedelta(days=1)
        self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {
            "estado": "publicada",
            "fecha_cierre_solicitudes_cambio_sede": limite.isoformat(),
            "fecha_limite_justificacion_autoridades": (limite + timedelta(days=1)).isoformat(),
        })
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.PUBLICADA)
        self.assertEqual(self.eleccion.fecha_cierre_solicitudes_cambio_sede, limite)
        self.assertIsNone(self.eleccion.fecha_limite_justificacion_autoridades)

    def test_publicacion_sin_permiso_no_modifica_estado_ni_plazos(self):
        self.client.force_login(get_user_model().objects.create_user(username="sin-permiso-publicar"))
        respuesta = self.client.post(reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {
            "estado": "publicada",
            "fecha_cierre_solicitudes_cambio_sede": "2026-10-01",
        })
        self.assertEqual(respuesta.status_code, 403)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_PREPARACION)
        self.assertIsNone(self.eleccion.fecha_cierre_solicitudes_cambio_sede)

    def test_filtro_solicitudes_con_estados_mezclados_y_en_modo_lectura(self):
        self.estado(Eleccion.Estado.PUBLICADA)
        solicitudes = []
        for indice, estado in enumerate(SolicitudCambioSede.Estado.values):
            solicitud = self.solicitud(self.crear_registro(f"4010010{indice}"))
            solicitud.estado = estado
            solicitud.save(update_fields=("estado",))
            solicitudes.append(solicitud)
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        for estado_eleccion in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.FINALIZADA):
            self.estado(estado_eleccion)
            for solicitud in solicitudes:
                with self.subTest(estado=solicitud.estado, eleccion=estado_eleccion):
                    respuesta = self.client.get(url, {"estado": solicitud.estado})
                    self.assertEqual(list(respuesta.context["solicitudes"]), [solicitud])
                    self.assertContains(respuesta, f"Estado: {solicitud.get_estado_display()}")
                    self.assertContains(respuesta, f'value="{solicitud.estado}" selected')
                    self.assertContains(respuesta, 'id="filtro-solicitudes"')
                    self.assertNotContains(respuesta, "Limpiar filtro")
            self.assertEqual(self.client.get(url).context["solicitudes"].count(), 3)

    def test_configuracion_en_curso_es_consultable_pero_post_bloqueado(self):
        self.verificar_configuracion_solo_lectura(Eleccion.Estado.EN_CURSO)

    def test_configuracion_publicada_es_consultable_pero_post_bloqueado(self):
        self.verificar_configuracion_solo_lectura(Eleccion.Estado.PUBLICADA)
        respuesta = self.client.get(reverse("configurar-eleccion", args=(self.eleccion.pk,)))
        self.assertContains(respuesta, "La configuración está en modo lectura.")
        self.assertContains(respuesta, "Consultar datos")

    def verificar_configuracion_solo_lectura(self, estado):
        self.estado(estado)
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
            if estado == Eleccion.Estado.PUBLICADA and nombre in ("gestionar-autoridades", "gestionar-autoridades-claustro"):
                continue
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
        self.estado(Eleccion.Estado.EN_CURSO)
        url = reverse("gestionar-fechas-administrativas", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["configuracion_solo_lectura"])
        self.assertEqual(self.client.post(url, {}).status_code, 302)
        self.mesa.estado_escaneo = Mesa.EstadoEscaneo.PROCESADA
        self.mesa.save(update_fields=("estado_escaneo",))
        self.assertEqual(self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)), {"estado": Eleccion.Estado.FINALIZADA},
        ).status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.FINALIZADA)

    def test_transicion_bloqueada_se_informa_como_popup(self):
        self.estado(Eleccion.Estado.EN_CURSO)
        respuesta = self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)),
            {"estado": Eleccion.Estado.FINALIZADA}, follow=True,
        )
        self.eleccion.refresh_from_db()
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.EN_CURSO)
        self.assertContains(respuesta, "data-popup-mensaje")
        self.assertContains(respuesta, 'data-popup-titulo="No se puede cambiar el estado"')
        self.assertContains(respuesta, "No se puede finalizar la elección con mesas pendientes de escaneo.")

    def test_popup_finalizacion_informa_periodo_de_justificacion_vigente_sin_bloquear(self):
        self.estado(Eleccion.Estado.EN_CURSO)
        fecha_limite = timezone.localdate() + timedelta(days=3)
        self.eleccion.justificacion_electores_habilitada_en = timezone.now()
        self.eleccion.fecha_limite_justificacion_electores = fecha_limite
        self.eleccion.save(
            update_fields=(
                "justificacion_electores_habilitada_en",
                "fecha_limite_justificacion_electores",
            )
        )
        self.mesa.estado_escaneo = Mesa.EstadoEscaneo.PROCESADA
        self.mesa.save(update_fields=("estado_escaneo",))

        respuesta = self.client.get(reverse("configurar-eleccion", args=(self.eleccion.pk,)))

        self.assertContains(respuesta, "Aún se encuentra vigente el período de justificación")
        self.assertContains(respuesta, f"{fecha_limite:%d/%m/%Y} inclusive.")
        self.assertContains(respuesta, "⚠ Aún se encuentra vigente el período de justificación")
        finalizacion = self.client.post(
            reverse("cambiar-estado-eleccion", args=(self.eleccion.pk,)),
            {"estado": Eleccion.Estado.FINALIZADA},
        )
        self.eleccion.refresh_from_db()
        self.assertEqual(finalizacion.status_code, 302)
        self.assertEqual(self.eleccion.estado, Eleccion.Estado.FINALIZADA)

    def test_popup_finalizacion_no_muestra_periodo_de_justificacion_vencido(self):
        self.estado(Eleccion.Estado.EN_CURSO)
        self.eleccion.justificacion_electores_habilitada_en = timezone.now() - timedelta(days=10)
        self.eleccion.fecha_limite_justificacion_electores = timezone.localdate() - timedelta(days=1)
        self.eleccion.save(
            update_fields=(
                "justificacion_electores_habilitada_en",
                "fecha_limite_justificacion_electores",
            )
        )

        respuesta = self.client.get(reverse("configurar-eleccion", args=(self.eleccion.pk,)))

        self.assertNotContains(respuesta, "Aún se encuentra vigente el período de justificación")

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
        for estado in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO, Eleccion.Estado.FINALIZADA):
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
        from apps.padron.models import AsignacionSedePadron
        self.estado(Eleccion.Estado.PUBLICADA)
        self.mesa.generada_automaticamente = True
        self.mesa.save(update_fields=("generada_automaticamente",))
        seleccionada = self.solicitud()
        no_seleccionada = self.solicitud(self.crear_registro("40100002"))
        for registro in (seleccionada.registro_padron, no_seleccionada.registro_padron):
            AsignacionSedePadron.objects.create(registro_padron=registro, sede=self.sedes[0], estado="asignada")
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        respuesta = self.client.get(url, {"accion": "estimar_seleccion", "solicitudes_ids": [seleccionada.pk]})
        self.assertEqual(respuesta.json(), {
            "mesas_por_sede": {str(self.sedes[1].pk): 1}, "mesas_quitadas_por_sede": {str(self.sedes[0].pk): 1},
            "total": 1, "total_quitadas": 1, "seleccionadas": 1,
        })
        respuesta = self.client.post(url, {
            "accion": "aprobar_seleccionadas", "solicitudes_ids": [seleccionada.pk],
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.client.post(url, {"accion": "confirmar_aprobacion", "propuesta": respuesta.context["propuesta"]}).status_code, 302)
        seleccionada.refresh_from_db()
        no_seleccionada.refresh_from_db()
        self.assertEqual(seleccionada.estado, SolicitudCambioSede.Estado.APROBADA)
        self.assertEqual(no_seleccionada.estado, SolicitudCambioSede.Estado.PENDIENTE)
        self.assertEqual(EnvioNotificacion.objects.count(), 1)

    def test_seleccion_invalida_o_vacia_no_resuelve_ninguna_solicitud(self):
        self.estado(Eleccion.Estado.PUBLICADA)
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
        self.estado(Eleccion.Estado.EN_CURSO)
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
        self.estado(Eleccion.Estado.PUBLICADA)
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

    def test_aprobar_cambio_quita_mesa_automatica_que_queda_vacia(self):
        self.estado(Eleccion.Estado.PUBLICADA)
        self.mesa.generada_automaticamente = True
        self.mesa.save(update_fields=("generada_automaticamente",))
        consulta = SolicitudCambioSede.objects.filter(pk=self.solicitud().pk)
        impacto = estimar_impacto_mesas_por_sede(self.eleccion, consulta)
        self.assertEqual(impacto, {"agregadas": {self.sedes[1].pk: 1}, "quitadas": {self.sedes[0].pk: 1}})
        respuesta = self.client.get(reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,)))
        self.assertContains(respuesta, "Se agregan: 1 mesa en Medrano.")
        self.assertContains(respuesta, "Se quitan: 1 mesa en Campus.")
        resolver_solicitudes_pendientes(self.eleccion, usuario=self.usuario, accion="aprobar_todas")
        self.assertFalse(Mesa.objects.filter(pk=self.mesa.pk).exists())
        self.assertEqual(list(Mesa.objects.values_list("sede", flat=True)), [self.sedes[1].pk])

    def test_aprobar_cambio_conserva_mesa_manual_vacia(self):
        self.estado(Eleccion.Estado.PUBLICADA)
        self.solicitud()
        resolver_solicitudes_pendientes(self.eleccion, usuario=self.usuario, accion="aprobar_todas")
        self.assertTrue(Mesa.objects.filter(pk=self.mesa.pk).exists())

    def test_resolucion_masiva_deshabilitada_sin_pendientes_y_filtro_por_estado(self):
        self.estado(Eleccion.Estado.PUBLICADA)
        solicitud = self.solicitud()
        solicitud.estado = SolicitudCambioSede.Estado.RECHAZADA
        solicitud.save(update_fields=("estado",))
        url = reverse("gestionar-solicitudes-cambio-sede", args=(self.eleccion.pk,))
        respuesta = self.client.get(url)
        self.assertContains(respuesta, "No hay solicitudes pendientes para resolver.")
        for texto in ("Aceptar todas sin límite de mesas nuevas", "Aceptar sin agregar mesas", "Rechazar todas"):
            self.assertContains(respuesta, f"disabled>{texto}</button>")
        self.assertEqual(list(self.client.get(url, {"estado": "pendiente"}).context["solicitudes"]), [])
        self.assertEqual(list(self.client.get(url, {"estado": "rechazada"}).context["solicitudes"]), [solicitud])
        self.assertEqual(self.client.get(url, {"estado": "otro"}).context["estado_filtro"], "")

    def test_solicitud_preselecciona_sede_si_hay_una_sola_opcion(self):
        from apps.padron.forms import FormularioSolicitudCambioSede

        formulario = FormularioSolicitudCambioSede(registro_padron=self.registro)
        self.assertEqual(formulario.fields["sede_destino"].initial, self.sedes[1].pk)
        self.assertIsNone(formulario.fields["sede_destino"].empty_label)

    def test_gestion_de_mesas_filtra_por_claustro_departamento_y_sede(self):
        otra = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sedes[1], eleccion_claustro_departamento=self.alcance,
        )
        url = reverse("gestionar-mesas", args=(self.eleccion.pk,))
        respuesta = self.client.get(url, {"sede": self.sedes[1].pk})
        self.assertEqual([mesa.pk for mesa in respuesta.context["mesas"]], [otra.pk])
        respuesta = self.client.get(url, {"claustro": self.configuracion.pk, "departamento": self.departamento.pk})
        self.assertEqual({mesa.pk for mesa in respuesta.context["mesas"]}, {self.mesa.pk, otra.pk})
        self.assertContains(respuesta, f"claustro={self.configuracion.pk}&amp;departamento={self.departamento.pk}")
    def test_inicio_admin_global_muestra_cuatro_cards_sin_acciones(self):
        respuesta = self.client.get(reverse("inicio-administrador-junta"))
        for titulo in ("Elección actual", "Justificativos pendientes", "Solicitudes de cambio de sede pendientes", "Participación"):
            self.assertContains(respuesta, titulo)
        self.assertContains(respuesta, '<article class="option">', count=4)
        self.assertNotContains(respuesta, "Revisar solicitudes")
        self.assertNotContains(respuesta, '<a class="button')
        self.eleccion.estado = Eleccion.Estado.FINALIZADA
        self.eleccion.save(update_fields=("estado",))
        self.assertContains(self.client.get(reverse("inicio-administrador-junta")), "Crear elección")

    def test_codigo_departamento_mesa_en_mail_y_cards_elector_y_autoridad(self):
        self.estado(Eleccion.Estado.EN_CURSO)
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
        self.estado(Eleccion.Estado.EN_CURSO)
        self.configuracion.eleccion = self.eleccion
        self.assertFalse(administrador.has_change_permission(peticion, self.configuracion))
        self.assertFalse(administrador.has_delete_permission(peticion, self.configuracion))
        with self.assertRaises(PermissionDenied):
            administrador.save_model(peticion, self.configuracion, None, True)
        with self.assertRaises(PermissionDenied):
            administrador.delete_model(peticion, self.configuracion)

    def test_participacion_del_inicio_solo_cuenta_votos_confirmados_en_mesas_procesadas(self):
        self.estado(Eleccion.Estado.EN_CURSO)
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
