from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

import qrcode

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.asistencia.dashboard import FiltrosDashboard, construir_dashboard
from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.elecciones.historial_electores import construir_historial_electoral
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.justificativos.forms import FormularioJustificativo
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.justificativos.services import resolver_justificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento
from apps.reportes.services import exportar_reporte_eleccion
from apps.usuarios.models import PerfilUsuario


class JustificacionDepartamentosMultiplesTests(TestCase):
    def setUp(self):
        ahora = timezone.now()
        self.eleccion = Eleccion.objects.create(
            nombre="Elección con mesas especiales", fecha_inicio=ahora,
            fecha_fin=ahora + timedelta(hours=8), estado=Eleccion.Estado.PUBLICADA,
            justificacion_electores_habilitada_en=ahora,
            fecha_limite_justificacion_electores=timezone.localdate() + timedelta(days=5),
            notificaciones_ausentes_confirmadas_en=ahora,
        )
        self.junta = get_user_model().objects.create_superuser(username="junta-justificaciones")
        self.usuario = get_user_model().objects.create_user(username="elector-justificaciones")
        self.elector = Elector.objects.create(legajo="1234", dni="40123456", nombre="Ana", apellido="Pérez")
        PerfilUsuario.objects.create(usuario=self.usuario, elector=self.elector)
        claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Estudiantes"),
        )
        self.registros = []
        for numero, codigo in enumerate(("K", "I"), start=1):
            alcance = EleccionClaustroDepartamento.objects.create(
                eleccion_claustro=claustro,
                departamento=Departamento.objects.create(codigo=codigo, nombre=f"Departamento {codigo}"),
            )
            registro = RegistroPadron.objects.create(
                eleccion=self.eleccion, elector=self.elector,
                eleccion_claustro_departamento=alcance, es_principal=numero == 1,
            )
            mesa = Mesa.objects.create(
                eleccion=self.eleccion, eleccion_claustro_departamento=alcance,
                numero=numero, es_especial=numero == 2, estado_escaneo=Mesa.EstadoEscaneo.PROCESADA,
            )
            AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
            self.registros.append(registro)
        self.tipo = TipoJustificativo.objects.create(nombre="Enfermedad")
        self.datos = {"ausencia": "votar", "tipo": self.tipo.pk, "detalle": "Reposo durante la jornada."}

    def marcar_ausencia(self, registro):
        return RegistroParticipacion.objects.create(
            registro_padron=registro, mesa=registro.asignacion_mesa.mesa,
            registrada_por=self.junta, metodo=RegistroParticipacion.Metodo.MANUAL,
        )

    def presentar(self, registro=None):
        formulario = FormularioJustificativo(self.datos, registro_padron=registro or self.registros[0])
        self.assertTrue(formulario.is_valid(), formulario.errors)
        return formulario.save()

    def historial(self):
        return {item["registro_id"]: item for item in construir_historial_electoral(self.elector)}

    def test_una_solicitud_y_resolucion_para_todas_las_ausencias(self):
        for registro in self.registros:
            self.marcar_ausencia(registro)
        justificativo = self.presentar()
        self.assertEqual(JustificativoAusencia.objects.count(), 1)
        self.assertEqual(set(justificativo.registros_cubiertos), set(self.registros))
        for item in self.historial().values():
            self.assertEqual(item["estado"], "Justificativo Pendiente de Revisión")
            self.assertEqual(item["justificativo"].pk, justificativo.pk)
        for estado, etiqueta in (
            ("aprobado", "Inasistencia Justificada"),
            ("rechazado", "Infractor - Justificación Rechazada"),
        ):
            resolver_justificativo(justificativo, estado=estado, observacion="Revisado", usuario=self.junta)
            self.assertEqual({item["estado"] for item in self.historial().values()}, {etiqueta})
        self.assertEqual(RegistroParticipacion.objects.count(), 2)

    def test_ausencia_solo_en_especial_se_presenta_desde_la_web(self):
        self.marcar_ausencia(self.registros[1])
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("mis-justificativos"))
        self.assertContains(respuesta, "Una sola justificación")
        self.assertTrue(respuesta.context["puede_presentar"])
        respuesta = self.client.post(reverse("mis-justificativos"), self.datos)
        self.assertEqual(respuesta.status_code, 302)
        justificativo = JustificativoAusencia.objects.get()
        self.assertEqual(justificativo.registro_padron_id, self.registros[1].pk)
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.junta)
        historial = self.historial()
        self.assertEqual(historial[self.registros[0].pk]["estado"], "Voto Emitido")
        self.assertEqual(historial[self.registros[1].pk]["estado"], "Inasistencia Justificada")

    def test_no_modifica_el_estado_de_una_mesa_donde_voto(self):
        self.marcar_ausencia(self.registros[0])
        justificativo = self.presentar()
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.junta)
        self.assertEqual(list(justificativo.registros_cubiertos), [self.registros[0]])
        self.assertEqual(self.historial()[self.registros[1].pk]["estado"], "Voto Emitido")

    def test_presentacion_desde_principal_sin_ausencia_usa_el_registro_ausente(self):
        self.marcar_ausencia(self.registros[1])
        justificativo = self.presentar(self.registros[0])
        self.assertEqual(justificativo.registro_padron_id, self.registros[1].pk)
        self.assertEqual(self.historial()[self.registros[0].pk]["estado"], "Voto Emitido")

    def test_impide_doble_presentacion_desde_otro_registro_y_formularios_previos(self):
        formularios = []
        for registro in self.registros:
            self.marcar_ausencia(registro)
            formulario = FormularioJustificativo(self.datos, registro_padron=registro)
            self.assertTrue(formulario.is_valid(), formulario.errors)
            formularios.append(formulario)
        formularios[0].save()
        with self.assertRaises(ValidationError):
            formularios[1].save()
        repetido = FormularioJustificativo(self.datos, registro_padron=self.registros[1])
        self.assertFalse(repetido.is_valid())
        self.assertEqual(JustificativoAusencia.objects.count(), 1)

    def test_cubre_ausencia_registrada_despues_sin_duplicar_solicitud(self):
        self.marcar_ausencia(self.registros[0])
        justificativo = self.presentar()
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.junta)
        self.marcar_ausencia(self.registros[1])
        self.assertEqual(self.historial()[self.registros[1].pk]["estado"], "Inasistencia Justificada")
        self.assertEqual(JustificativoAusencia.objects.count(), 1)

    def test_no_cubre_a_otra_persona_ni_otra_eleccion(self):
        self.marcar_ausencia(self.registros[0])
        justificativo = self.presentar()
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.junta)
        otra_persona = Elector.objects.create(legajo="5678", dni="40987654", nombre="Luis", apellido="Otro")
        registro_otro = RegistroPadron.objects.create(
            elector=otra_persona, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.registros[0].eleccion_claustro_departamento,
        )
        RegistroParticipacion.objects.create(
            registro_padron=registro_otro, mesa=self.registros[0].asignacion_mesa.mesa,
            registrada_por=self.junta, metodo="manual",
        )
        self.assertIsNone(construir_historial_electoral(otra_persona)[0]["justificativo"])
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.FINALIZADA)
        otra_eleccion = Eleccion.objects.create(
            nombre="Otra elección", fecha_inicio=self.eleccion.fecha_inicio + timedelta(days=30),
            fecha_fin=self.eleccion.fecha_fin + timedelta(days=30), estado=Eleccion.Estado.PUBLICADA,
        )
        otro_claustro = EleccionClaustro.objects.create(
            eleccion=otra_eleccion, claustro=self.registros[0].eleccion_claustro_departamento.eleccion_claustro.claustro,
        )
        otro_alcance = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=otro_claustro, departamento=self.registros[0].eleccion_claustro_departamento.departamento,
        )
        otro_registro = RegistroPadron.objects.create(
            elector=self.elector, eleccion=otra_eleccion, eleccion_claustro_departamento=otro_alcance,
        )
        self.assertIsNone(self.historial()[otro_registro.pk]["justificativo"])
        self.assertEqual(list(justificativo.registros_cubiertos), [self.registros[0]])

    def test_dashboard_y_filtro_departamental_reflejan_la_cobertura(self):
        for registro in self.registros:
            self.marcar_ausencia(registro)
        justificativo = self.presentar()
        pendiente = construir_dashboard(self.junta, self.eleccion, FiltrosDashboard())
        self.assertEqual(pendiente["justificativos_recibidos"], 2)
        self.assertEqual(pendiente["justificativos_confirmados"], 0)
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.junta)
        filtros = FiltrosDashboard(departamento_id=self.registros[1].eleccion_claustro_departamento.departamento_id)
        especial = construir_dashboard(self.junta, self.eleccion, filtros)
        self.assertEqual(especial["justificativos_recibidos"], 1)
        self.assertEqual(especial["justificativos_confirmados"], 1)

    def test_infractores_aplica_una_resolucion_a_ambas_mesas(self):
        for registro in self.registros:
            self.marcar_ausencia(registro)
        justificativo = self.presentar()
        resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.junta)
        csv = exportar_reporte_eleccion(self.eleccion, "infractores").content.decode("utf-8-sig")
        self.assertEqual(len(csv.splitlines()), 1)
        resolver_justificativo(justificativo, estado="rechazado", observacion="", usuario=self.junta)
        csv = exportar_reporte_eleccion(self.eleccion, "infractores").content.decode("utf-8-sig")
        self.assertEqual(csv.count("rechazado"), 2)

    def test_justificativo_como_autoridad_no_cubre_ausencias_a_votar(self):
        for registro in self.registros:
            self.marcar_ausencia(registro)
        JustificativoAusencia.objects.create(
            registro_padron=self.registros[0], ausencia="autoridad", tipo=self.tipo,
            detalle="No puedo asistir como autoridad.", estado="aprobado",
        )
        self.assertTrue(all(item["justificativo"] is None for item in self.historial().values()))
        datos = construir_dashboard(self.junta, self.eleccion, FiltrosDashboard())
        self.assertEqual(datos["justificativos_recibidos"], 0)
        self.assertEqual(datos["justificativos_confirmados"], 0)
        self.presentar()

    def test_reclamo_de_participacion_conserva_el_alcance_de_su_comprobante(self):
        for registro in self.registros:
            self.marcar_ausencia(registro)
        reclamo = JustificativoAusencia.objects.create(
            registro_padron=self.registros[0], ausencia="votar", reclamo_participacion=True,
            detalle="Voté en la mesa principal.", comprobante_extraviado=True,
        )
        self.assertEqual(list(reclamo.registros_cubiertos), [self.registros[0]])
        self.assertEqual(self.historial()[self.registros[0].pk]["justificativo"].pk, reclamo.pk)
        self.assertIsNone(self.historial()[self.registros[1].pk]["justificativo"])

    def preparar_reclamo_multiple(self):
        for registro in self.registros:
            self.marcar_ausencia(registro)
        return {"reclamo_participacion": "on", "comprobante_extraviado": "on", "detalle": "Voté en la mesa indicada."}

    def test_reclamo_exige_elegir_mesa_si_hay_varias_ausencias(self):
        formulario = FormularioJustificativo(self.preparar_reclamo_multiple(), registro_padron=self.registros[0])
        self.assertFalse(formulario.is_valid())
        self.assertIn("registro_reclamado", formulario.errors)
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("mis-justificativos"))
        self.assertContains(respuesta, 'name="registro_reclamado"')
        self.assertContains(respuesta, "Mesa donde votaste")

    def test_reclamo_selecciona_especial_y_su_aprobacion_conserva_ausencia_principal(self):
        datos = self.preparar_reclamo_multiple()
        datos["registro_reclamado"] = self.registros[1].pk
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(reverse("mis-justificativos"), datos).status_code, 302)
        justificativo = JustificativoAusencia.objects.get()
        self.assertEqual(justificativo.registro_padron_id, self.registros[1].pk)
        self.client.force_login(self.junta)
        ruta = reverse("resolver-justificativo", args=(justificativo.pk,))
        self.assertContains(self.client.get(ruta), "Mesa reclamada")
        with patch("apps.justificativos.views.enviar_notificacion", return_value=True) as enviar:
            self.assertEqual(self.client.post(ruta, {"estado": "aprobado"}).status_code, 302)
        enviar.assert_called_once()
        self.assertTrue(self.registros[0].participaciones.exists())
        self.assertFalse(self.registros[1].participaciones.exists())
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("mis-justificativos"))
        self.assertTrue(respuesta.context["formulario"].permite_reclamo())

    def test_reclamo_rechaza_la_mesa_de_otra_persona(self):
        datos = self.preparar_reclamo_multiple()
        otro = Elector.objects.create(legajo="9000", dni="40999999", nombre="Otro", apellido="Elector")
        ajeno = RegistroPadron.objects.create(
            elector=otro, eleccion=self.eleccion, eleccion_claustro_departamento=self.registros[0].eleccion_claustro_departamento,
        )
        datos["registro_reclamado"] = ajeno.pk
        formulario = FormularioJustificativo(datos, registro_padron=self.registros[0])
        self.assertFalse(formulario.is_valid())
        self.assertIn("registro_reclamado", formulario.errors)
        self.assertFalse(JustificativoAusencia.objects.exists())

    def test_revalida_ausencia_de_la_mesa_seleccionada_al_guardar(self):
        datos = self.preparar_reclamo_multiple()
        datos["registro_reclamado"] = self.registros[1].pk
        formulario = FormularioJustificativo(datos, registro_padron=self.registros[0])
        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.registros[1].participaciones.all().delete()
        with self.assertRaises(ValidationError):
            formulario.save()
        self.assertFalse(JustificativoAusencia.objects.exists())

    def test_justificativo_normal_ignora_el_selector_y_cubre_ambas_ausencias(self):
        self.preparar_reclamo_multiple()
        datos = {**self.datos, "registro_reclamado": "999999999"}
        formulario = FormularioJustificativo(datos, registro_padron=self.registros[0])
        self.assertTrue(formulario.is_valid(), formulario.errors)
        justificativo = formulario.save()
        self.assertFalse(justificativo.reclamo_participacion)
        self.assertEqual(set(justificativo.registros_cubiertos), set(self.registros))

    def imagen_comprobante(self, registro):
        codigo = ServicioRegistroParticipacion.generar_codigo_qr(
            eleccion_id=self.eleccion.pk, mesa_numero=registro.asignacion_mesa.mesa.numero,
            identificador_qr=registro.identificador_qr,
        )
        archivo = BytesIO()
        qrcode.make(codigo).get_image().convert("RGB").save(archivo, format="PNG")
        return SimpleUploadedFile("troquel.png", archivo.getvalue(), content_type="image/png")

    def test_comprobante_de_especial_se_valida_con_su_propio_qr(self):
        datos = self.preparar_reclamo_multiple()
        datos.update(registro_reclamado=self.registros[1].pk, comprobante_extraviado="")
        self.client.force_login(self.usuario)
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            datos["documento"] = self.imagen_comprobante(self.registros[1])
            self.assertEqual(self.client.post(reverse("mis-justificativos"), datos).status_code, 302)
            justificativo = JustificativoAusencia.objects.get()
            self.assertEqual(justificativo.registro_padron_id, self.registros[1].pk)
            self.assertEqual(justificativo.validacion_comprobante, "valido")

    def test_comprobante_principal_no_acredita_voto_en_especial(self):
        datos = self.preparar_reclamo_multiple()
        datos.update(registro_reclamado=self.registros[1].pk, comprobante_extraviado="")
        self.client.force_login(self.usuario)
        with TemporaryDirectory() as directorio, override_settings(MEDIA_ROOT=directorio):
            datos["documento"] = self.imagen_comprobante(self.registros[0])
            self.assertEqual(self.client.post(reverse("mis-justificativos"), datos).status_code, 302)
            self.assertEqual(JustificativoAusencia.objects.get().validacion_comprobante, "invalido")
        self.assertEqual(RegistroParticipacion.objects.count(), 2)
