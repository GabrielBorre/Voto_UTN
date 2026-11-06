from datetime import datetime, timedelta
from io import BytesIO
from smtplib import SMTPException
from unittest.mock import patch
from tempfile import TemporaryDirectory

import qrcode
from PIL import Image
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.test import override_settings
from django.utils import timezone
from django.utils.timezone import make_aware
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.auditoria.models import EventoAuditoria
from apps.autoridades.models import AsignacionAutoridad
from apps.justificativos.forms import FormularioJustificativo
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import Mesa
from apps.notificaciones.models import EnvioNotificacion
from apps.mesas.models import Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Turno
from apps.usuarios.models import AsignacionRol, PerfilUsuario
from apps.usuarios.backend_auth import ElectorUser


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
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.FINALIZADA)
        eleccion_reciente = Eleccion.objects.create(
            nombre="Elección reciente",
            fecha_inicio=make_aware(datetime(2026, 9, 3, 8)),
            fecha_fin=make_aware(datetime(2026, 9, 3, 16)),
            estado=Eleccion.Estado.PUBLICADA,
            habilitada=True,
        )
        registro_reciente = self.crear_registro_padron(elector, eleccion_reciente)
        usuario = get_user_model().objects.create_user(username="elector", password="clave")
        PerfilUsuario.objects.create(usuario=usuario, elector=elector)
        return usuario, registro_anterior, registro_reciente

    def preparar_reclamo_participacion(self):
        usuario, _, registro = self.crear_elector_con_padrones()
        mesa = Mesa.objects.create(
            eleccion=registro.eleccion, numero=1,
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            estado_escaneo=Mesa.EstadoEscaneo.PROCESADA,
        )
        self.registrar_no_votante(registro, mesa)
        self.client.force_login(usuario)
        return usuario, registro, mesa

    def test_casilla_reclamo_se_muestra_y_oculta_ausencia_y_tipo(self):
        self.preparar_reclamo_participacion()
        respuesta = self.client.get(reverse("mis-justificativos"))
        self.assertContains(respuesta, "Voté, pero aparezco como ausente")
        self.assertContains(respuesta, 'data-campo-justificativo="ausencia"')
        self.assertContains(respuesta, 'data-campo-justificativo="tipo"')
        self.assertContains(respuesta, "js/mis-justificativos.js")
        self.assertContains(respuesta, 'aria-describedby="ayuda_reclamo_participacion"')
        self.assertContains(respuesta, 'aria-describedby="ayuda_comprobante_extraviado"')
        self.assertContains(respuesta, 'title="Marcá esta opción si votaste y figurás como ausente.')
        self.assertNotContains(respuesta, "<small>Marcá esta opción")

    def test_casilla_reclamo_no_se_ofrece_sin_ausencia_registrada(self):
        usuario, _, registro = self.crear_elector_con_padrones()
        registro.eleccion.justificacion_electores_habilitada_en = timezone.now()
        registro.eleccion.save(update_fields=("justificacion_electores_habilitada_en",))
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("mis-justificativos"))
        self.assertNotContains(respuesta, "Voté, pero aparezco como ausente")
        self.assertNotContains(respuesta, "Perdí el comprobante de votación")
        formulario = FormularioJustificativo(
            {"reclamo_participacion": True, "comprobante_extraviado": True, "detalle": "Voté."},
            registro_padron=registro,
        )
        self.assertFalse(formulario.permite_reclamo())
        self.assertFalse(formulario.is_valid())
        self.assertFalse(JustificativoAusencia.objects.filter(registro_padron=registro).exists())

    def test_reclamo_admite_comprobante_sin_ausencia_ni_tipo_y_conserva_participacion(self):
        _, registro, _ = self.preparar_reclamo_participacion()
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            respuesta = self.client.post(reverse("mis-justificativos"), {
                "reclamo_participacion": "on", "detalle": "Voté y adjunto el comprobante.",
                "documento": SimpleUploadedFile("comprobante.pdf", b"%PDF-1.4\ncomprobante"),
            })
            self.assertRedirects(respuesta, reverse("mis-justificativos"))
            justificativo = JustificativoAusencia.objects.get(registro_padron=registro)
            self.assertTrue(justificativo.reclamo_participacion)
            self.assertIsNone(justificativo.tipo)
            self.assertEqual(justificativo.ausencia, JustificativoAusencia.Ausencia.VOTAR)
            self.assertTrue(justificativo.documento)
            self.assertFalse(justificativo.comprobante_extraviado)
            self.assertEqual(justificativo.estado, JustificativoAusencia.Estado.PENDIENTE)
            self.assertEqual(justificativo.validacion_comprobante, JustificativoAusencia.ValidacionComprobante.NO_PROCESABLE)
            self.assertTrue(registro.participaciones.exists())
            self.assertContains(self.client.get(reverse("mis-justificativos")), "Voté, pero aparezco como ausente")

    def test_reclamo_ignora_ausencia_y_tipo_enviados(self):
        _, registro, _ = self.preparar_reclamo_participacion()
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad reclamo")
        datos = {
            "reclamo_participacion": True, "ausencia": "autoridad", "tipo": tipo.pk,
            "detalle": "Perdí el comprobante.", "comprobante_extraviado": True,
        }
        formulario = FormularioJustificativo(datos, registro_padron=registro)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        justificativo = formulario.save()
        self.assertEqual(justificativo.ausencia, JustificativoAusencia.Ausencia.VOTAR)
        self.assertIsNone(justificativo.tipo)

    def test_reclamo_con_comprobante_extraviado_se_muestra_al_revisor(self):
        _, registro, _ = self.preparar_reclamo_participacion()
        respuesta = self.client.post(reverse("mis-justificativos"), {
            "reclamo_participacion": "on", "detalle": "Perdí el comprobante. Voté por la mañana.",
            "comprobante_extraviado": "on",
        })
        self.assertRedirects(respuesta, reverse("mis-justificativos"))
        justificativo = JustificativoAusencia.objects.get(registro_padron=registro)
        self.assertTrue(justificativo.comprobante_extraviado)
        self.assertFalse(justificativo.documento)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("resolver-justificativo", args=(justificativo.pk,)))
        self.assertContains(respuesta, "Requiere revisión manual del padrón")
        self.assertContains(respuesta, "Voté, pero aparezco como ausente")
        self.assertEqual(justificativo.validacion_comprobante, JustificativoAusencia.ValidacionComprobante.SIN_COMPROBANTE)

    def imagen_qr(self, contenido, nombre="comprobante.png"):
        salida = BytesIO()
        if contenido is None:
            Image.new("RGB", (200, 200), "white").save(salida, format="PNG")
        else:
            qrcode.make(contenido).get_image().convert("RGB").save(salida, format="PNG")
        return SimpleUploadedFile(nombre, salida.getvalue(), content_type="image/png")

    def qr_troquel(self, registro, mesa, eleccion_id=None, identificador=None):
        return ServicioRegistroParticipacion.generar_codigo_qr(
            eleccion_id=eleccion_id or registro.eleccion_id,
            mesa_numero=mesa.numero,
            identificador_qr=identificador or registro.identificador_qr,
        )

    def presentar_reclamo(self, registro, documento):
        respuesta = self.client.post(reverse("mis-justificativos"), {
            "reclamo_participacion": "on", "detalle": "Voté y adjunto el troquel.", "documento": documento,
        })
        self.assertRedirects(respuesta, reverse("mis-justificativos"))
        return JustificativoAusencia.objects.get(registro_padron=registro)

    def test_comprobante_con_qr_del_elector_se_valida_y_la_aprobacion_anula_la_ausencia(self):
        _, registro, mesa = self.preparar_reclamo_participacion()
        participacion = registro.participaciones.get()
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            justificativo = self.presentar_reclamo(registro, self.imagen_qr(self.qr_troquel(registro, mesa)))
            self.assertEqual(justificativo.validacion_comprobante, JustificativoAusencia.ValidacionComprobante.VALIDO)
            self.assertIsNotNone(justificativo.comprobante_validado_en)
            # La validación automática no anula la ausencia: requiere aprobación de la Junta.
            self.assertTrue(registro.participaciones.exists())
            self.client.force_login(self.usuario)
            url = reverse("resolver-justificativo", args=(justificativo.pk,))
            respuesta = self.client.get(url)
            self.assertContains(respuesta, "QR válido para el elector")
            self.assertContains(respuesta, "El QR corresponde al elector y a la mesa 1.")
            self.client.post(url, {"estado": "aprobado", "observacion_resolucion": ""})
        justificativo.refresh_from_db()
        self.assertFalse(registro.participaciones.exists())
        self.assertIsNotNone(justificativo.participacion_anulada_en)
        self.assertEqual(justificativo.respaldo_participacion["id"], participacion.pk)
        self.assertEqual(justificativo.respaldo_participacion["mesa_id"], mesa.pk)
        evento = EventoAuditoria.objects.get(accion="participacion.anulada_por_reclamo")
        self.assertEqual(evento.usuario, self.usuario)
        self.assertEqual(evento.datos_anteriores["registro_padron_id"], registro.pk)

        self.client.post(url, {"estado": "rechazado", "observacion_resolucion": "Revisado."})
        justificativo.refresh_from_db()
        restaurada = registro.participaciones.get()
        self.assertEqual(restaurada.mesa, mesa)
        self.assertEqual(restaurada.registrada_en, participacion.registrada_en)
        self.assertIsNone(justificativo.participacion_anulada_en)
        self.assertTrue(EventoAuditoria.objects.filter(accion="participacion.restaurada_por_reclamo").exists())

    def test_comprobante_invalido_queda_para_revision_y_el_rechazo_conserva_la_ausencia(self):
        _, registro, mesa = self.preparar_reclamo_participacion()
        otro = RegistroPadron.objects.create(
            elector=Elector.objects.create(legajo="9001", nombre="Otro", apellido="Elector", dni="40000001"),
            eleccion=registro.eleccion, eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
        )
        Validacion = JustificativoAusencia.ValidacionComprobante
        valido = self.qr_troquel(registro, mesa)
        adulterado = valido[:-1] + ("Y" if valido.endswith("Z") else "Z")
        casos = (
            (self.qr_troquel(registro, mesa, identificador=otro.identificador_qr), Validacion.INVALIDO, "otro elector"),
            (self.qr_troquel(registro, mesa, eleccion_id=self.eleccion.pk), Validacion.INVALIDO, "otra elección"),
            (adulterado, Validacion.INVALIDO, "no es un comprobante firmado"),
            (None, Validacion.NO_DETECTADO, "No se encontró un código QR"),
        )
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            for contenido, esperado, detalle in casos:
                with self.subTest(esperado=esperado, detalle=detalle):
                    JustificativoAusencia.objects.filter(registro_padron=registro).delete()
                    justificativo = self.presentar_reclamo(registro, self.imagen_qr(contenido))
                    self.assertEqual(justificativo.validacion_comprobante, esperado)
                    self.assertIn(detalle, justificativo.detalle_validacion_comprobante)
            self.client.force_login(self.usuario)
            url = reverse("resolver-justificativo", args=(justificativo.pk,))
            self.assertContains(self.client.get(url), "No se detectó un QR")
            self.client.post(url, {"estado": "rechazado", "observacion_resolucion": "Sin QR."})
        self.assertTrue(registro.participaciones.exists())
        self.assertFalse(EventoAuditoria.objects.filter(accion="participacion.anulada_por_reclamo").exists())

    def test_revalidar_comprobante_y_solo_la_junta_puede_resolver(self):
        usuario_elector, registro, mesa = self.preparar_reclamo_participacion()
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            justificativo = self.presentar_reclamo(registro, self.imagen_qr(self.qr_troquel(registro, mesa)))
            JustificativoAusencia.objects.filter(pk=justificativo.pk).update(
                validacion_comprobante=JustificativoAusencia.ValidacionComprobante.PENDIENTE,
            )
            url = reverse("resolver-justificativo", args=(justificativo.pk,))
            self.assertEqual(self.client.post(url, {"estado": "aprobado"}).status_code, 403)
            self.assertEqual(self.client.post(url, {"accion": "revalidar"}).status_code, 403)
            self.assertTrue(registro.participaciones.exists())
            self.client.force_login(self.usuario)
            self.assertRedirects(self.client.post(url, {"accion": "revalidar"}), url)
        justificativo.refresh_from_db()
        self.assertEqual(justificativo.validacion_comprobante, JustificativoAusencia.ValidacionComprobante.VALIDO)
        self.assertEqual(justificativo.estado, JustificativoAusencia.Estado.PENDIENTE)
        self.assertTrue(registro.participaciones.exists())

    def test_reclamo_rechaza_falta_de_comprobante_o_de_comentario(self):
        _, registro, _ = self.preparar_reclamo_participacion()
        for adicionales in ({}, {"comprobante_extraviado": "on", "detalle": "  "}):
            with self.subTest(adicionales=adicionales):
                respuesta = self.client.post(reverse("mis-justificativos"), {
                    "reclamo_participacion": "on", "detalle": "Voté.", **adicionales,
                })
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["formulario"].errors)
                self.assertFalse(JustificativoAusencia.objects.filter(registro_padron=registro).exists())

    def test_sin_reclamo_exige_ausencia_y_tipo_e_ignora_comprobante_extraviado(self):
        _, registro, _ = self.preparar_reclamo_participacion()
        formulario = FormularioJustificativo({"detalle": "Enfermedad."}, registro_padron=registro)
        self.assertFalse(formulario.is_valid())
        self.assertIn("ausencia", formulario.errors)
        self.assertIn("tipo", formulario.errors)
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad sin reclamo")
        formulario = FormularioJustificativo(
            {"ausencia": "votar", "tipo": tipo.pk, "detalle": "Enfermedad.", "comprobante_extraviado": True},
            registro_padron=registro,
        )
        self.assertTrue(formulario.is_valid(), formulario.errors)
        justificativo = formulario.save()
        self.assertFalse(justificativo.reclamo_participacion)
        self.assertFalse(justificativo.comprobante_extraviado)

    def test_reclamo_no_disponible_si_ya_justifico_ausencia_a_votar(self):
        _, registro, _ = self.preparar_reclamo_participacion()
        datos = {"reclamo_participacion": True, "detalle": "Perdí el comprobante.", "comprobante_extraviado": True}
        formulario = FormularioJustificativo(
            datos, {"documento": SimpleUploadedFile("comprobante.exe", b"invalido")}, registro_padron=registro,
        )
        self.assertFalse(formulario.is_valid())
        self.assertIn("documento", formulario.errors)
        formulario = FormularioJustificativo(datos, registro_padron=registro)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        formulario.save()
        siguiente = FormularioJustificativo(datos, registro_padron=registro)
        self.assertTrue(siguiente.fields["reclamo_participacion"].disabled)
        self.assertFalse(siguiente.is_valid())
        self.assertEqual(registro.justificativos.count(), 1)

    def test_plazo_autoridades_inclusivo_no_afecta_justificativos_elector(self):
        usuario, registro, mesa = self.preparar_reclamo_participacion()
        turno = Turno.objects.create(nombre="Mañana plazo", hora_inicio="08:00", hora_fin="12:00")
        AsignacionAutoridad.objects.bulk_create([
            AsignacionAutoridad(registro_padron=registro, mesa=mesa, turno=turno, asignada_por=usuario),
        ])
        registro.eleccion.estado = Eleccion.Estado.PUBLICADA
        registro.eleccion.autoridades_confirmadas_en = timezone.now()
        registro.eleccion.save(update_fields=("estado", "autoridades_confirmadas_en"))
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad plazo")
        for dias in (-1, 0, 1):
            with self.subTest(dias=dias):
                registro.eleccion.fecha_limite_justificacion_autoridades = timezone.localdate() + timedelta(days=dias)
                registro.eleccion.save(update_fields=("fecha_limite_justificacion_autoridades",))
                datos = {"ausencia": "autoridad", "tipo": tipo.pk, "detalle": "Enfermedad."}
                formulario = FormularioJustificativo(datos, registro_padron=registro)
                self.assertEqual(formulario.is_valid(), dias >= 0, formulario.errors)
                datos["ausencia"] = "votar"
                self.assertTrue(FormularioJustificativo(datos, registro_padron=registro).is_valid())

    def registrar_no_votante(self, registro, mesa=None):
        registro.eleccion.justificacion_electores_habilitada_en = timezone.now()
        registro.eleccion.fecha_limite_justificacion_electores = timezone.localdate() + timedelta(days=5)
        registro.eleccion.save(
            update_fields=("justificacion_electores_habilitada_en", "fecha_limite_justificacion_electores")
        )
        mesa = mesa or Mesa.objects.create(
            eleccion=registro.eleccion,
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            numero=registro.pk,
        )
        return RegistroParticipacion.objects.create(
            registro_padron=registro,
            mesa=mesa,
            registrada_por=self.usuario,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )

    def test_mis_justificativos_muestra_la_eleccion_mas_reciente_sin_selector(self):
        usuario, _, registro_reciente = self.crear_elector_con_padrones()
        self.client.login(username=usuario.username, password="clave")

        respuesta = self.client.get(reverse("mis-justificativos"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["eleccion"], registro_reciente.eleccion)
        self.assertContains(respuesta, registro_reciente.eleccion.nombre)
        self.assertNotContains(respuesta, 'name="registro_padron"')

    def test_presentacion_habilitada_en_elecciones_publicadas_y_en_curso(self):
        usuario, _, registro = self.crear_elector_con_padrones()
        self.registrar_no_votante(registro)
        self.client.force_login(usuario)

        for estado in (Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO):
            with self.subTest(estado=estado):
                Eleccion.objects.filter(pk=registro.eleccion_id).update(estado=estado)

                respuesta = self.client.get(reverse("mis-justificativos"))

                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context["eleccion"].estado, estado)
                self.assertTrue(respuesta.context["estado_habilitado"])
                self.assertTrue(respuesta.context["puede_presentar"])
                self.assertContains(respuesta, 'id="btn-presentar"')

    def test_presentacion_bloqueada_en_eleccion_en_preparacion(self):
        usuario, _, registro = self.crear_elector_con_padrones()
        Eleccion.objects.filter(pk=registro.eleccion_id).update(estado=Eleccion.Estado.EN_PREPARACION)
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse("mis-justificativos"),
            {"ausencia": "votar", "tipo": tipo.id, "detalle": "Detalle."},
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.context["estado_habilitado"])
        self.assertNotContains(respuesta, 'id="btn-presentar"')
        self.assertContains(respuesta, "únicamente para elecciones publicadas o en curso")
        self.assertFalse(JustificativoAusencia.objects.filter(registro_padron=registro).exists())

    def test_mis_justificativos_ignora_un_registro_padron_alterado_en_post(self):
        usuario, registro_anterior, registro_reciente = self.crear_elector_con_padrones()
        self.registrar_no_votante(registro_reciente)
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
        self.registrar_no_votante(registro_reciente)
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        datos = {"ausencia": "votar", "tipo": tipo.id, "detalle": "Detalle."}
        self.client.login(username=usuario.username, password="clave")

        self.client.post(reverse("mis-justificativos"), datos)
        respuesta = self.client.post(reverse("mis-justificativos"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(JustificativoAusencia.objects.filter(registro_padron=registro_reciente).count(), 1)

    def test_autoridad_puede_presentar_un_justificativo_por_tipo_de_ausencia(self):
        from django.utils import timezone
        from apps.autoridades.models import AsignacionAutoridad
        from apps.mesas.models import Mesa
        from apps.parametros.models import Sede, Turno

        usuario, _, registro = self.crear_elector_con_padrones()
        Eleccion.objects.filter(pk=registro.eleccion_id).update(autoridades_confirmadas_en=timezone.now(), fecha_limite_justificacion_autoridades=timezone.localdate() + timedelta(days=1))
        tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        sede = Sede.objects.create(nombre="Central")
        turno = Turno.objects.create(nombre="Mañana", hora_inicio="08:00", hora_fin="12:00")
        mesa = Mesa.objects.create(
            eleccion=registro.eleccion,
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            sede=sede,
            numero=1,
        )
        self.registrar_no_votante(registro, mesa)
        AsignacionAutoridad.objects.bulk_create([
            AsignacionAutoridad(registro_padron=registro, mesa=mesa, turno=turno, asignada_por=usuario)
        ])
        self.client.login(username=usuario.username, password="clave")

        for ausencia in ("votar", "autoridad", "autoridad"):
            self.client.post(reverse("mis-justificativos"), {"ausencia": ausencia, "tipo": tipo.id, "detalle": "x"})

        self.assertEqual(JustificativoAusencia.objects.filter(registro_padron=registro).count(), 2)

    def test_autoridad_no_puede_presentar_justificativo_en_eleccion_en_curso(self):
        from apps.autoridades.models import AsignacionAutoridad
        from apps.mesas.models import Mesa
        from apps.parametros.models import Sede, Turno

        usuario, _, registro = self.crear_elector_con_padrones()
        Eleccion.objects.filter(pk=registro.eleccion_id).update(estado=Eleccion.Estado.EN_CURSO)
        tipo = TipoJustificativo.objects.create(nombre="Motivo autoridad en curso")
        turno = Turno.objects.create(nombre="Tarde", hora_inicio="13:00", hora_fin="17:00")
        mesa = Mesa.objects.create(
            eleccion=registro.eleccion,
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            sede=Sede.objects.create(nombre="Campus autoridad"),
            numero=1,
        )
        AsignacionAutoridad.objects.bulk_create(
            [AsignacionAutoridad(registro_padron=registro, mesa=mesa, turno=turno, asignada_por=usuario)]
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse("mis-justificativos"),
            {"ausencia": "autoridad", "tipo": tipo.id, "detalle": "No puede asistir."},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(
            JustificativoAusencia.objects.filter(
                registro_padron=registro,
                ausencia=JustificativoAusencia.Ausencia.AUTORIDAD,
            ).exists()
        )
    def test_no_habilita_justificacion_de_voto_sin_periodo_abierto_o_registro_de_no_voto(self):
        usuario, _, registro = self.crear_elector_con_padrones()
        mesa = Mesa.objects.create(
            eleccion=registro.eleccion,
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            numero=registro.pk,
        )
        RegistroParticipacion.objects.create(
            registro_padron=registro,
            mesa=mesa,
            registrada_por=usuario,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("mis-justificativos"))

        self.assertFalse(respuesta.context["puede_presentar_justificativo_electoral"])
        self.assertContains(respuesta, "La justificación por inasistencia estará disponible")

    def test_no_habilita_justificacion_de_voto_si_no_hay_registro_de_no_voto(self):
        usuario, _, registro = self.crear_elector_con_padrones()
        registro.eleccion.justificacion_electores_habilitada_en = timezone.now()
        registro.eleccion.fecha_limite_justificacion_electores = timezone.localdate() + timedelta(days=5)
        registro.eleccion.save(
            update_fields=("justificacion_electores_habilitada_en", "fecha_limite_justificacion_electores")
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("mis-justificativos"))

        self.assertFalse(respuesta.context["puede_presentar_justificativo_electoral"])

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
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.FINALIZADA)
        self.client.force_login(self.usuario)
        url = reverse("resolver-justificativo", args=(justificativo.id,))

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "está en el historial.")
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
        notificacion = EnvioNotificacion.objects.get(elector=justificativo.registro_padron.elector)
        self.assertEqual(notificacion.asunto, mail.outbox[0].subject)
        self.assertEqual(notificacion.contenido, mail.outbox[0].body)
        self.assertEqual(notificacion.estado, EnvioNotificacion.Estado.ENVIADO)
        self.assertIsNotNone(notificacion.enviada_en)
        self.assertIsNone(notificacion.leida_en)
        self.client.force_login(
            ElectorUser(justificativo.registro_padron.elector.dni),
            backend="apps.usuarios.backend_auth.ElectorBackend",
        )
        listado = self.client.get(reverse("mis-notificaciones"))
        self.assertContains(listado, notificacion.asunto)
        self.assertEqual(listado.context["notificaciones_no_leidas"], 1)
        detalle = self.client.get(reverse("leer-notificacion", args=(notificacion.pk,)))
        self.assertEqual(detalle.context["notificacion"].contenido, mail.outbox[0].body)
        notificacion.refresh_from_db()
        self.assertIsNotNone(notificacion.leida_en)

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
        notificacion = EnvioNotificacion.objects.get(elector=justificativo.registro_padron.elector)
        self.assertEqual(notificacion.contenido, mail.outbox[0].body)

    def test_resolucion_conserva_notificacion_web_si_falla_el_correo(self):
        justificativo = self.crear_justificativo()
        self.client.force_login(self.usuario)

        with patch("apps.notificaciones.services.send_mail", side_effect=SMTPException("fallo simulado")):
            with self.assertLogs("apps.notificaciones.services", level="WARNING"):
                respuesta = self.client.post(
                    reverse("resolver-justificativo", args=(justificativo.pk,)),
                    {"estado": "aprobado", "observacion_resolucion": "Validada."},
                    follow=True,
                )

        self.assertContains(respuesta, "la notificación está disponible en la web")
        justificativo.refresh_from_db()
        self.assertEqual(justificativo.estado, JustificativoAusencia.Estado.APROBADO)
        notificacion = EnvioNotificacion.objects.get(elector=justificativo.registro_padron.elector)
        self.assertEqual(notificacion.estado, EnvioNotificacion.Estado.ERROR)
        self.assertIn("Validada.", notificacion.contenido)

    def test_error_al_crear_notificacion_no_deja_justificativo_resuelto_sin_aviso(self):
        justificativo = self.crear_justificativo()
        self.client.force_login(self.usuario)

        with patch("apps.justificativos.views.crear_notificacion_resultado_justificativo", side_effect=ValueError("fallo simulado")):
            with self.assertRaises(ValueError):
                self.client.post(
                    reverse("resolver-justificativo", args=(justificativo.pk,)),
                    {"estado": "aprobado", "observacion_resolucion": "Validada."},
                )

        justificativo.refresh_from_db()
        self.assertEqual(justificativo.estado, JustificativoAusencia.Estado.PENDIENTE)
        self.assertIsNone(justificativo.resuelta_en)
        self.assertFalse(EnvioNotificacion.objects.exists())

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
