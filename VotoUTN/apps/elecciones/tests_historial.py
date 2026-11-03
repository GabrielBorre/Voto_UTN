from datetime import timedelta
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.justificativos.forms import FormularioJustificativo
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.usuarios.backend_auth import ElectorUser
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class HistorialElectoralTests(TestCase):
    def setUp(self):
        self.hoy = timezone.localdate()
        self.claustro = Claustro.objects.create(nombre="Docentes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="HIST")
        self.elector = Elector.objects.create(
            legajo="historial-1",
            nombre="María",
            apellido="López",
            dni="12345678",
        )
        self.usuario = get_user_model().objects.create_user(username="electora-historial")
        PerfilUsuario.objects.create(usuario=self.usuario, elector=self.elector)
        self.eleccion_abierta, self.registro_abierto, self.mesa_abierta = self.crear_registro(
            "Elección en curso",
            Eleccion.Estado.EN_CURSO,
            numero=1,
        )
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ELECTOR,
            eleccion=self.eleccion_abierta,
        )
        self.tipo = TipoJustificativo.objects.create(nombre="Motivo personal")

    def crear_registro(self, nombre, estado, numero):
        fecha = self.hoy - timedelta(days=365)
        eleccion = Eleccion.objects.create(
            nombre=nombre,
            fecha_inicio=fecha,
            fecha_fin=fecha,
            estado=estado,
            habilitada=estado == Eleccion.Estado.EN_CURSO,
        )
        claustro_eleccion = EleccionClaustro.objects.create(
            eleccion=eleccion,
            claustro=self.claustro,
        )
        alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=claustro_eleccion,
            departamento=self.departamento,
        )
        registro = RegistroPadron.objects.create(
            elector=self.elector,
            eleccion=eleccion,
            eleccion_claustro_departamento=alcance,
        )
        from apps.mesas.models import Mesa

        mesa = Mesa.objects.create(
            eleccion=eleccion,
            eleccion_claustro_departamento=alcance,
            numero=numero,
        )
        return eleccion, registro, mesa

    def habilitar_periodo(self, eleccion, limite=None):
        eleccion.justificacion_electores_habilitada_en = timezone.now() - timedelta(minutes=1)
        eleccion.fecha_limite_justificacion_electores = limite or (self.hoy + timedelta(days=5))
        eleccion.save(
            update_fields=("justificacion_electores_habilitada_en", "fecha_limite_justificacion_electores")
        )

    def confirmar_notificaciones_ausentes(self, eleccion):
        eleccion.notificaciones_ausentes_confirmadas_en = timezone.now() - timedelta(minutes=1)
        eleccion.save(update_fields=("notificaciones_ausentes_confirmadas_en",))

    def registrar_no_voto(self, registro, mesa):
        return RegistroParticipacion.objects.create(
            registro_padron=registro,
            mesa=mesa,
            registrada_por=self.usuario,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )

    def crear_justificativo(self, registro, estado):
        return JustificativoAusencia.objects.create(
            registro_padron=registro,
            ausencia=JustificativoAusencia.Ausencia.VOTAR,
            tipo=self.tipo,
            detalle="Detalle de la solicitud.",
            estado=estado,
        )

    def test_historial_calcula_los_estados_con_la_regla_de_no_votantes(self):
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)

        elecciones = {}
        for nombre in ("Votó", "No registrado", "Pendiente", "Aprobado", "Rechazado", "Infractor"):
            elecciones[nombre] = self.crear_registro(
                nombre,
                Eleccion.Estado.FINALIZADA,
                numero=len(elecciones) + 2,
            )
            self.confirmar_notificaciones_ausentes(elecciones[nombre][0])

        votado, registro_votado, _ = elecciones["Votó"]
        self.habilitar_periodo(votado)

        sin_registro, registro_sin_justificar, mesa_sin_justificar = elecciones["No registrado"]
        self.habilitar_periodo(sin_registro)
        self.registrar_no_voto(registro_sin_justificar, mesa_sin_justificar)

        pendiente, registro_pendiente, mesa_pendiente = elecciones["Pendiente"]
        self.habilitar_periodo(pendiente)
        self.registrar_no_voto(registro_pendiente, mesa_pendiente)
        self.crear_justificativo(registro_pendiente, JustificativoAusencia.Estado.PENDIENTE)

        aprobado, registro_aprobado, mesa_aprobado = elecciones["Aprobado"]
        self.habilitar_periodo(aprobado)
        self.registrar_no_voto(registro_aprobado, mesa_aprobado)
        self.crear_justificativo(registro_aprobado, JustificativoAusencia.Estado.APROBADO)

        rechazado, registro_rechazado, mesa_rechazado = elecciones["Rechazado"]
        self.habilitar_periodo(rechazado)
        self.registrar_no_voto(registro_rechazado, mesa_rechazado)
        self.crear_justificativo(registro_rechazado, JustificativoAusencia.Estado.RECHAZADO)

        infractor, registro_infractor, mesa_infractor = elecciones["Infractor"]
        self.habilitar_periodo(infractor, self.hoy - timedelta(days=1))
        self.registrar_no_voto(registro_infractor, mesa_infractor)

        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("historial-electoral"))

        self.assertEqual(respuesta.status_code, 200)
        estados = {item["eleccion"].nombre: item["estado"] for item in respuesta.context["historial"]}
        self.assertEqual(estados, {
            "Elección en curso": "En Curso",
            "Votó": "Voto Emitido",
            "No registrado": "En Curso - Voto No Registrado",
            "Pendiente": "Pendiente de Revisión",
            "Aprobado": "Inasistencia Justificada",
            "Rechazado": "Infractor - Justificación Rechazada",
            "Infractor": "Infractor",
        })
        self.assertContains(respuesta, "El período de justificación está habilitado.")
        self.assertContains(respuesta, "Historial Electoral")
        for estado in (
            "Voto Emitido",
            "En Curso - Voto No Registrado",
            "Pendiente de Revisión",
            "Inasistencia Justificada",
            "Infractor - Justificación Rechazada",
            "Infractor",
        ):
            self.assertContains(respuesta, estado)
        self.assertContains(respuesta, '<span aria-hidden="true">✔</span>', count=2)
        self.assertContains(respuesta, '<span aria-hidden="true">❌</span>', count=2)
        self.assertContains(respuesta, '<span aria-hidden="true">⏳</span>', count=1)
        self.assertContains(respuesta, '<span aria-hidden="true">⚠</span>', count=1)

    def test_eleccion_publicada_antes_del_periodo_aparece_con_situacion_en_curso(self):
        self.eleccion_abierta.estado = Eleccion.Estado.PUBLICADA
        self.eleccion_abierta.save(update_fields=("estado",))
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        justificativo = self.crear_justificativo(
            self.registro_abierto,
            JustificativoAusencia.Estado.APROBADO,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial-electoral"))

        self.assertEqual(respuesta.status_code, 200)
        historial = {
            item["eleccion"].pk: item["estado"]
            for item in respuesta.context["historial"]
        }
        self.assertEqual(historial[self.eleccion_abierta.pk], "En Curso")
        self.assertEqual(
            respuesta.context["historial"][0]["justificativo"],
            justificativo,
        )
        self.assertContains(respuesta, "En Curso")

    def test_eleccion_finalizada_muestra_infractor_si_hay_ausencia_sin_justificativo(self):
        self.eleccion_abierta.estado = Eleccion.Estado.FINALIZADA
        self.eleccion_abierta.save(update_fields=("estado",))
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        votada, _, _ = self.crear_registro(
            "Elección finalizada con voto",
            Eleccion.Estado.FINALIZADA,
            numero=2,
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial-electoral"))

        historial = {
            item["eleccion"].pk: item
            for item in respuesta.context["historial"]
        }
        self.assertEqual(
            historial[self.eleccion_abierta.pk]["estado"],
            "Infractor",
        )
        self.assertEqual(historial[votada.pk]["estado"], "Voto Emitido")

    def test_confirmar_notificaciones_muestra_ausencia_aunque_no_se_haya_abierto_justificativo(self):
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        self.confirmar_notificaciones_ausentes(self.eleccion_abierta)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial-electoral"))

        historial = {
            item["eleccion"].pk: item["estado"]
            for item in respuesta.context["historial"]
        }
        self.assertEqual(
            historial[self.eleccion_abierta.pk],
            "En Curso - Voto No Registrado",
        )
        self.assertContains(respuesta, '<span aria-hidden="true">⚠</span>')

    def test_ausente_pasa_a_infractor_al_vencer_el_periodo_de_justificacion(self):
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        self.habilitar_periodo(self.eleccion_abierta, limite=self.hoy + timedelta(days=1))
        self.confirmar_notificaciones_ausentes(self.eleccion_abierta)
        self.client.force_login(self.usuario)

        durante_periodo = self.client.get(reverse("historial-electoral"))
        self.assertEqual(
            durante_periodo.context["historial"][0]["estado"],
            "En Curso - Voto No Registrado",
        )

        self.eleccion_abierta.fecha_limite_justificacion_electores = self.hoy - timedelta(days=1)
        self.eleccion_abierta.save(update_fields=("fecha_limite_justificacion_electores",))
        vencido = self.client.get(reverse("historial-electoral"))
        self.assertEqual(vencido.context["historial"][0]["estado"], "Infractor")

    def test_confirmar_notificaciones_muestra_voto_emitido_si_no_hay_ausencia(self):
        self.confirmar_notificaciones_ausentes(self.eleccion_abierta)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial-electoral"))

        historial = {
            item["eleccion"].pk: item["estado"]
            for item in respuesta.context["historial"]
        }
        self.assertEqual(historial[self.eleccion_abierta.pk], "Voto Emitido")
        self.assertContains(respuesta, '<span aria-hidden="true">✔</span>')

    def test_confirmar_eleccion_actual_no_cambia_situacion_de_eleccion_anterior(self):
        anterior, registro_anterior, mesa_anterior = self.crear_registro(
            "Elección anterior",
            Eleccion.Estado.FINALIZADA,
            numero=2,
        )
        self.confirmar_notificaciones_ausentes(anterior)
        self.registrar_no_voto(registro_anterior, mesa_anterior)
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        self.confirmar_notificaciones_ausentes(self.eleccion_abierta)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial-electoral"))

        estados = {
            item["eleccion"].pk: item["estado"]
            for item in respuesta.context["historial"]
        }
        self.assertEqual(estados[anterior.pk], "En Curso - Voto No Registrado")
        self.assertEqual(estados[self.eleccion_abierta.pk], "En Curso - Voto No Registrado")

    def test_justificativo_se_muestra_despues_de_confirmar_notificaciones(self):
        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        self.habilitar_periodo(self.eleccion_abierta)
        self.crear_justificativo(self.registro_abierto, JustificativoAusencia.Estado.APROBADO)
        self.confirmar_notificaciones_ausentes(self.eleccion_abierta)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("historial-electoral"))

        historial = {
            item["eleccion"].pk: item["estado"]
            for item in respuesta.context["historial"]
        }
        self.assertEqual(historial[self.eleccion_abierta.pk], "Inasistencia Justificada")

    def test_formulario_solo_habilita_justificacion_electoral_en_periodo_y_con_ausencia(self):
        formulario = FormularioJustificativo(registro_padron=self.registro_abierto)
        self.assertNotIn(
            JustificativoAusencia.Ausencia.VOTAR,
            dict(formulario.fields["ausencia"].choices),
        )

        self.registrar_no_voto(self.registro_abierto, self.mesa_abierta)
        formulario = FormularioJustificativo(registro_padron=self.registro_abierto)
        self.assertNotIn(
            JustificativoAusencia.Ausencia.VOTAR,
            dict(formulario.fields["ausencia"].choices),
        )

        self.habilitar_periodo(self.eleccion_abierta)
        formulario = FormularioJustificativo(registro_padron=self.registro_abierto)
        self.assertIn(
            JustificativoAusencia.Ausencia.VOTAR,
            dict(formulario.fields["ausencia"].choices),
        )

    def test_historial_solo_es_accesible_para_elector_o_autoridad(self):
        usuario_sin_rol = get_user_model().objects.create_user(username="sin-rol")
        elector_sin_rol = Elector.objects.create(
            legajo="historial-sin-rol",
            nombre="Sin",
            apellido="Rol",
            dni="12345679",
        )
        PerfilUsuario.objects.create(usuario=usuario_sin_rol, elector=elector_sin_rol)
        self.client.force_login(usuario_sin_rol)

        respuesta = self.client.get(reverse("historial-electoral"))

        self.assertEqual(respuesta.status_code, 403)
        self.assertNotContains(respuesta, "Historial Electoral", status_code=403)

        autoridad = get_user_model().objects.create_user(username="autoridad-historial")
        elector_autoridad = Elector.objects.create(
            legajo="historial-autoridad",
            nombre="Autoridad",
            apellido="Electoral",
            dni="12345680",
        )
        PerfilUsuario.objects.create(usuario=autoridad, elector=elector_autoridad)
        AsignacionRol.objects.create(
            usuario=autoridad,
            rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=self.eleccion_abierta,
            mesa=self.mesa_abierta,
        )
        self.client.force_login(autoridad)
        self.assertEqual(self.client.get(reverse("historial-electoral")).status_code, 200)

    def test_solicitud_y_adjunto_solo_son_visibles_para_su_elector(self):
        eleccion, registro, _ = self.crear_registro(
            "Elección con justificativo",
            Eleccion.Estado.FINALIZADA,
            numero=2,
        )
        justificativo = self.crear_justificativo(registro, JustificativoAusencia.Estado.APROBADO)
        self.client.force_login(self.usuario)

        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            justificativo.documento.save("certificado.pdf", ContentFile(b"PDF de prueba"))
            url_detalle = reverse("detalle-justificativo-elector", args=(justificativo.pk,))
            url_documento = reverse("documento-justificativo-elector", args=(justificativo.pk,))
            url_media = f"/media/{justificativo.documento.name}"

            respuesta = self.client.get(url_detalle)
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, eleccion.nombre)
            self.assertContains(respuesta, "Vista previa del adjunto")
            self.assertContains(respuesta, url_documento)
            respuesta_documento = self.client.get(url_documento)
            self.assertEqual(b"".join(respuesta_documento.streaming_content), b"PDF de prueba")
            respuesta_media = self.client.get(url_media)
            self.assertEqual(b"".join(respuesta_media.streaming_content), b"PDF de prueba")

            otro_elector = Elector.objects.create(
                legajo="historial-otro",
                nombre="Otro",
                apellido="Elector",
                dni="87654321",
            )
            otro_usuario = get_user_model().objects.create_user(username="otro-elector")
            PerfilUsuario.objects.create(usuario=otro_usuario, elector=otro_elector)
            AsignacionRol.objects.create(
                usuario=otro_usuario,
                rol=AsignacionRol.Rol.ELECTOR,
                eleccion=self.eleccion_abierta,
            )
            self.client.force_login(otro_usuario)
            self.assertEqual(self.client.get(url_detalle).status_code, 404)
            self.assertEqual(self.client.get(url_documento).status_code, 404)
            self.assertEqual(self.client.get(url_media).status_code, 404)


class HistorialElectoralElectorSinPadronTests(TestCase):
    def test_elector_ausente_del_padron_puede_ver_historial_vacio(self):
        usuario = ElectorUser("87654321")
        self.client.force_login(
            usuario,
            backend="apps.usuarios.backend_auth.ElectorBackend",
        )

        respuesta = self.client.get(reverse("historial-electoral"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["historial"], [])
        self.assertContains(respuesta, "No hay elecciones disponibles en tu historial.")
        self.assertContains(respuesta, reverse("historial-electoral"))
