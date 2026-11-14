from unittest.mock import patch
from tempfile import TemporaryDirectory

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.autoridades import tests as base
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades, ImportacionNominaAutoridades
from apps.autoridades.seleccion_manual import asignar_manualmente


class NominaAutomaticaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.directorio_archivos = TemporaryDirectory()
        cls.configuracion_archivos = override_settings(MEDIA_ROOT=cls.directorio_archivos.name)
        cls.configuracion_archivos.enable()

    @classmethod
    def tearDownClass(cls):
        cls.configuracion_archivos.disable()
        cls.directorio_archivos.cleanup()
        super().tearDownClass()

    def setUp(self):
        base.TurnosAutoridadesTests.setUp(self)
        self.opciones = ConfiguracionAutoridades.objects.create(eleccion_claustro=self.eleccion_claustro, modo="aleatorio")
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=2, suplentes_por_mesa=0)
        self.ruta = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        self.client.force_login(self.usuario)

    def cargar(self, documentos=None, *, confirmar=True, **opciones):
        documentos = documentos if documentos is not None else [r.elector.dni for r in self.registros]
        archivo = SimpleUploadedFile("nomina.csv", ("Documento\n" + "\n".join(documentos) + "\n").encode())
        respuesta = self.client.post(self.ruta, {"aplicar-modo": "1", "modo": "nomina", "archivo": archivo, **opciones}, follow=True)
        if confirmar and respuesta.context and respuesta.context.get("propuesta_nomina"):
            return self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        return respuesta

    def test_carga_distribuye_y_reporta_personas_no_cupos(self):
        respuesta = self.cargar()
        self.assertEqual(respuesta.status_code, 200)
        resumen = respuesta.context["resumen_nomina"]
        self.assertEqual((resumen["titulares"], resumen["suplentes"], resumen["sin_asignar"]), (2, 0, 1))
        self.assertEqual(resumen["total"], 3)
        self.assertEqual(len(resumen["escenarios"]), 5)
        self.assertContains(respuesta, "Se asignaron 2 titulares; 1 personas quedaron sin asignar.")
        self.assertNotContains(respuesta, "Agregar elector manualmente")
        self.assertNotContains(respuesta, "Aplicar nómina común")
        importacion = ImportacionNominaAutoridades.objects.get()
        self.assertEqual(importacion.estado, "confirmada")
        self.assertEqual(importacion.cantidad_validas, 3)
        self.assertIsNotNone(importacion.confirmada_en)
        self.assertContains(respuesta, "Historial de archivos de nómina")
        descarga = self.client.get(reverse("descargar-importacion-nomina", args=(self.eleccion.pk, self.eleccion_claustro.pk, importacion.pk)))
        self.assertEqual(descarga.status_code, 200)
        self.assertIn(b"Documento", b"".join(descarga.streaming_content))

    def test_archivo_invalido_queda_registrado_con_error(self):
        respuesta = self.cargar(["00000000"], confirmar=False)
        importacion = ImportacionNominaAutoridades.objects.get()
        self.assertEqual(importacion.estado, "rechazada")
        self.assertTrue(importacion.errores)
        self.assertContains(respuesta, "Historial de archivos de nómina")

    def test_importacion_acepta_csv_con_punto_y_coma(self):
        archivo = SimpleUploadedFile("nomina.csv", (
            "Tipo documento;Documento;Legajo\nDNI;" + self.registros[0].elector.dni + ";" + self.registros[0].elector.legajo + "\n"
        ).encode())
        respuesta = self.client.post(self.ruta, {"aplicar-modo": "1", "modo": "nomina", "archivo": archivo}, follow=True)
        self.assertContains(respuesta, "Revisar distribución propuesta")
        self.assertEqual(ImportacionNominaAutoridades.objects.get().cantidad_validas, 1)

    def test_nomina_rechaza_misma_persona_por_documento_y_legajo(self):
        from apps.autoridades.services import validar_csv_autoridades

        elector = self.registros[0].elector
        contenido = f"Documento;Legajo\n{elector.dni};\n;{elector.legajo}\n".encode()
        _, errores = validar_csv_autoridades(contenido, self.eleccion_claustro, "nomina.csv")
        self.assertTrue(any(numero == 3 and "repetido" in mensaje for numero, mensaje in errores))

    def test_historial_conserva_cancelacion_y_restringe_descarga(self):
        from django.contrib.auth import get_user_model
        self.cargar(confirmar=False)
        importacion = ImportacionNominaAutoridades.objects.get()
        self.client.post(self.ruta, {"cancelar-nomina": "1"})
        importacion.refresh_from_db()
        self.assertEqual(importacion.estado, "cancelada")
        intruso = get_user_model().objects.create_user(username="sin_permiso_archivo")
        self.client.force_login(intruso)
        url = reverse("descargar-importacion-nomina", args=(self.eleccion.pk, self.eleccion_claustro.pk, importacion.pk))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_importar_nomina_conserva_asignacion_manual_y_completa_vacantes(self):
        from django.contrib.auth import get_user_model
        from apps.usuarios.models import AsignacionRol, PerfilUsuario
        usuario_autoridad = get_user_model().objects.create_user(username="autoridad-conservada")
        PerfilUsuario.objects.create(usuario=usuario_autoridad, elector=self.registros[0].elector)
        anterior = asignar_manualmente(self.mesa, self.manana, self.registros[0], self.usuario, tipo="titular")
        rol_id = AsignacionRol.objects.get(usuario=usuario_autoridad, rol=AsignacionRol.Rol.AUTORIDAD_MESA).pk
        respuesta = self.cargar([r.elector.dni for r in self.registros[1:]])
        self.assertEqual(respuesta.status_code, 200)
        anterior.refresh_from_db()
        self.assertEqual((anterior.mesa_id, anterior.turno_id, anterior.tipo), (self.mesa.pk, self.manana.pk, "titular"))
        self.assertTrue(AsignacionRol.objects.filter(pk=rol_id, activo=True).exists())
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)

    def test_previsualizar_no_guarda_y_cancelar_no_modifica(self):
        respuesta = self.cargar(confirmar=False)
        self.assertContains(respuesta, "Revisar distribución propuesta")
        self.assertEqual(len(respuesta.context["propuesta_nomina"]["alternativas"]), 5)
        self.assertIn("mesa_distinta", {fila["codigo"] for fila in respuesta.context["propuesta_nomina"]["alternativas"]})
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.assertFalse(AsignacionAutoridad.objects.exists())
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")
        self.client.post(self.ruta, {"cancelar-nomina": "1"})
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.assertNotContains(self.client.get(self.ruta), "Revisar distribución propuesta")

    def test_elegir_alternativa_de_la_tabla_aplica_opciones_calculadas(self):
        respuesta = self.cargar(confirmar=False)
        self.assertContains(respuesta, 'name="alternativa"')
        self.assertNotContains(respuesta, 'name="reacomodar_titulares"')
        self.assertFalse(AsignacionAutoridad.objects.exists())
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1", "alternativa": "mesa_distinta"}, follow=True)
        self.assertContains(respuesta, "Se asignaron")
        self.opciones.refresh_from_db()
        self.assertTrue(self.opciones.permitir_mesa_distinta)
        self.assertFalse(self.opciones.reacomodar_titulares)
        self.assertEqual(ImportacionNominaAutoridades.objects.get().estado, "confirmada")

    def test_no_acepta_alternativa_ajena_a_la_previsualizacion(self):
        self.cargar(confirmar=False)
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1", "alternativa": "inventada"}, follow=True)
        self.assertContains(respuesta, "Elegí una alternativa disponible")
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_acciones_anteriores_de_nomina_no_eluden_la_revision(self):
        self.opciones.modo = "nomina"
        self.opciones.save()
        archivo = SimpleUploadedFile("nomina.csv", ("Documento\n" + self.registros[0].elector.dni + "\n").encode())
        respuesta = self.client.post(self.ruta, {"cargar-candidatos": "1", "csv-archivo": archivo}, follow=True)
        self.assertContains(respuesta, "Revisar distribución propuesta")
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.assertFalse(AsignacionAutoridad.objects.exists())
        self.client.post(self.ruta, {"cancelar-nomina": "1"})
        respuesta = self.client.post(self.ruta, {"aplicar-distribucion": "1"}, follow=True)
        self.assertContains(respuesta, "Revisar distribución propuesta")
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_accion_anterior_de_cambio_de_sede_no_aplica_cambios(self):
        self.opciones.modo = "nomina"
        self.opciones.save()
        respuesta = self.client.post(self.ruta, {"confirmar-cambio-sede": "1"}, follow=True)
        self.assertContains(respuesta, "revisá y confirmá la propuesta de nómina")
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_datos_cambiados_invalidan_previsualizacion(self):
        self.cargar(confirmar=False)
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=3)
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        self.assertContains(respuesta, "Los datos cambiaron desde la previsualización")
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_cambio_de_minimo_invalida_previsualizacion(self):
        self.cargar(confirmar=False)
        self.eleccion_claustro.turnos_autoridad.update(minimo_titulares_por_mesa=2)
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        self.assertContains(respuesta, "Los datos cambiaron desde la previsualización")
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_cambio_tipo_mesa_invalida_previsualizacion(self):
        self.cargar(confirmar=False)
        self.mesa.es_especial = True
        self.mesa.save(update_fields=("es_especial",))
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        self.assertContains(respuesta, "Los datos cambiaron desde la previsualización")
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_cambio_registro_principal_invalida_previsualizacion(self):
        self.cargar(confirmar=False)
        self.registros[0].es_principal = False
        self.registros[0].save(update_fields=("es_principal",))
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        self.assertContains(respuesta, "Los datos cambiaron desde la previsualización")
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_edicion_manual_descarta_previsualizacion_anterior(self):
        self.cargar(confirmar=False)
        ruta = reverse("seleccionar-autoridades-mesa", args=(self.eleccion.pk, self.eleccion_claustro.pk, self.mesa.pk))
        self.client.post(ruta, {"seleccionar": "1", "turno": self.manana.pk,
                               "tipo": "titular", "registro": self.registros[0].pk})
        self.assertTrue(AsignacionAutoridad.objects.filter(registro_padron=self.registros[0]).exists())
        self.assertNotContains(self.client.get(self.ruta), "Revisar distribución propuesta")

    def test_fallo_al_confirmar_revierte_nomina_y_asignaciones(self):
        self.cargar(confirmar=False, reacomodar_titulares="on")
        with patch("apps.autoridades.reordenamiento_padron.aplicar_padrones", side_effect=ValidationError("No se pudo guardar el padrón")):
            respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        self.assertContains(respuesta, "No se pudo guardar el padrón")
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.assertFalse(AsignacionAutoridad.objects.exists())
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")

    def test_no_mueve_sede_si_hay_solicitud_pendiente(self):
        from apps.mesas.models import Mesa
        from apps.padron.models import SolicitudCambioSede
        Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede,
                            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, suplentes_por_mesa=0)
        for registro in self.registros[:2]:
            SolicitudCambioSede.objects.create(
                registro_padron=registro, sede_origen=self.sede_votacion, sede_destino=self.sede,
            )
        respuesta = self.cargar(
            [r.elector.dni for r in self.registros[:2]], confirmar=False,
            permitir_cambio_sede="on", reacomodar_titulares="on",
        )
        self.assertContains(respuesta, "solicitud de cambio de sede pendiente")
        self.assertFalse(AsignacionAutoridad.objects.exists())
        self.assertFalse(CandidaturaAutoridad.objects.exists())

    def test_traslado_compatible_no_reordena_otros_electores(self):
        from apps.mesas.models import AsignacionMesa, Mesa
        destino = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede,
                                      eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, suplentes_por_mesa=0)
        antes = dict(AsignacionMesa.objects.values_list("registro_padron_id", "mesa_id"))
        respuesta = self.cargar([r.elector.dni for r in self.registros[:2]], permitir_cambio_sede="on")
        self.assertContains(respuesta, "Se asignaron 2 titulares")
        trasladada = AsignacionAutoridad.objects.get(mesa=destino).registro_padron
        self.assertEqual(trasladada.asignacion_mesa.mesa_id, destino.pk)
        self.assertEqual(trasladada.asignacion_sede_padron.sede_id, destino.sede_id)
        despues = dict(AsignacionMesa.objects.values_list("registro_padron_id", "mesa_id"))
        self.assertEqual({pk for pk in antes if antes[pk] != despues[pk]}, {trasladada.pk})

    def test_traslado_sin_reordenar_rechaza_mesa_fuera_de_orden(self):
        from apps.autoridades.reordenamiento_padron import traslado_sin_reordenar
        from apps.mesas.models import AsignacionMesa, Mesa
        primera = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede,
                                     eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        ultima = Mesa.objects.create(eleccion=self.eleccion, numero=3, sede=self.sede,
                                    eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        AsignacionMesa.objects.filter(registro_padron=self.registros[1]).update(mesa=primera)
        self.assertFalse(traslado_sin_reordenar(self.registros[0], ultima))

    def test_previsualiza_y_crea_mesa_aunque_queden_titulares_pendientes(self):
        from apps.mesas.models import AsignacionMesa, Mesa
        from apps.padron.models import AsignacionSedePadron, Elector, RegistroPadron
        self.eleccion_claustro.maximo_votantes_por_mesa = 2
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, suplentes_por_mesa=0)
        destino = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, sede=self.sede,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
            generada_automaticamente=True,
        )
        registro_c = self.registros[2]
        AsignacionMesa.objects.filter(registro_padron=registro_c).update(mesa=destino)
        AsignacionSedePadron.objects.filter(registro_padron=registro_c).update(sede=self.sede)
        elector = Elector.objects.create(dni="40999888", legajo="AUT-D", nombre="Elector D")
        registro_d = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion,
            eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
        )
        AsignacionSedePadron.objects.create(registro_padron=registro_d, sede=self.sede, estado="asignada")
        AsignacionMesa.objects.create(registro_padron=registro_d, mesa=destino)
        antes = list(AsignacionMesa.objects.order_by("registro_padron_id").values_list("registro_padron_id", "mesa_id"))
        respuesta = self.cargar(
            [self.registros[0].elector.dni, self.registros[1].elector.dni], confirmar=False,
        )
        self.assertContains(respuesta, "Revisar distribución propuesta")
        propuesta = respuesta.context["propuesta_nomina"]["resumen"]
        alternativas = {a["codigo"]: a for a in respuesta.context["propuesta_nomina"]["alternativas"]}
        self.assertEqual(alternativas["mesa_actual"]["titulares"], 1)
        self.assertEqual(alternativas["cambio_mesa"]["titulares"], 1)
        self.assertEqual(alternativas["sede_reacomodo"]["titulares"], 2)
        self.assertGreater(alternativas["sede_reacomodo"]["electores_cambian_sede"], 0)
        self.assertTrue(alternativas["sede_reacomodo"]["detalle_cambios_sede"])
        self.assertEqual(propuesta["titulares_faltantes"], 1)
        self.assertTrue(any(c["antes"] == 1 and c["despues"] == 2 for c in alternativas["sede_reacomodo"]["cambios"]))
        self.assertEqual(Mesa.objects.filter(eleccion=self.eleccion).count(), 2)
        self.assertEqual(list(AsignacionMesa.objects.order_by("registro_padron_id").values_list("registro_padron_id", "mesa_id")), antes)
        from apps.auditoria.models import EventoAuditoria
        self.assertFalse(EventoAuditoria.objects.filter(accion="autoridades.padron_reordenado").exists())
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1", "alternativa": "sede_reacomodo"}, follow=True)
        self.assertContains(respuesta, "Se asignaron 2 titulares")
        self.assertTrue(EventoAuditoria.objects.filter(accion="autoridades.padron_reordenado").exists())
        self.assertEqual(Mesa.objects.filter(eleccion=self.eleccion).count(), 3)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)
        for autoridad in AsignacionAutoridad.objects.filter(tipo="titular").select_related("registro_padron__asignacion_mesa", "registro_padron__asignacion_sede_padron", "mesa"):
            self.assertEqual(autoridad.registro_padron.asignacion_mesa.mesa_id, autoridad.mesa_id)
            self.assertEqual(autoridad.registro_padron.asignacion_sede_padron.sede_id, autoridad.mesa.sede_id)
            autoridad.full_clean()
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id", "turno_id", "tipo"))
        nueva = Mesa.objects.get(eleccion=self.eleccion, numero=3)
        registro_nuevo = AsignacionMesa.objects.filter(mesa=nueva).select_related("registro_padron__elector").first().registro_padron
        respuesta = self.cargar([registro_nuevo.elector.dni], confirmar=False, permitir_cambio_sede="on", reacomodar_titulares="on")
        self.assertContains(respuesta, "Revisar distribución propuesta")
        self.assertEqual(respuesta.context["propuesta_nomina"]["resumen"]["titulares_faltantes"], 0)
        respuesta = self.client.post(self.ruta, {"confirmar-nomina": "1"}, follow=True)
        self.assertContains(respuesta, "Se asignaron 3 titulares")
        self.assertTrue(anteriores.issubset(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id", "turno_id", "tipo"))))

    def test_misma_sede_reordena_el_padron_y_reserva_titulares_al_final(self):
        from apps.mesas.models import AsignacionMesa, Mesa
        self.eleccion_claustro.maximo_votantes_por_mesa = 2
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1, suplentes_por_mesa=0)
        otra = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                   eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
                                   generada_automaticamente=True)
        AsignacionMesa.objects.filter(registro_padron=self.registros[2]).update(mesa=otra)
        respuesta = self.cargar([self.registros[0].elector.dni, self.registros[1].elector.dni],
                                confirmar=False, reacomodar_titulares="on")
        self.assertContains(respuesta, "No se agregan ni se quitan mesas")
        self.client.post(self.ruta, {"confirmar-nomina": "1"})
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)
        for autoridad in AsignacionAutoridad.objects.filter(tipo="titular").select_related("registro_padron__asignacion_mesa"):
            fila = autoridad.registro_padron.asignacion_mesa
            self.assertEqual(fila.mesa_id, autoridad.mesa_id)
            self.assertTrue(fila.autoridad_al_final)
        self.assertEqual(AsignacionMesa.objects.count(), 3)
        self.assertTrue(all(m.asignaciones_padron.count() <= 2 for m in (self.mesa, otra)))

    def test_reordenar_conserva_los_titulares_ya_asignados(self):
        from apps.mesas.models import AsignacionMesa, Mesa
        self.eleccion_claustro.maximo_votantes_por_mesa = 2
        self.eleccion_claustro.save(update_fields=("maximo_votantes_por_mesa",))
        otra = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                   eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento,
                                   generada_automaticamente=True)
        titular = asignar_manualmente(self.mesa, self.manana, self.registros[0], self.usuario, tipo="titular")
        segundo_titular = asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="titular")
        respuesta = self.cargar([self.registros[2].elector.dni], reacomodar_titulares="on")
        self.assertContains(respuesta, "Se asignaron 3 titulares")
        titular.refresh_from_db()
        segundo_titular.refresh_from_db()
        self.assertEqual(titular.mesa_id, self.mesa.pk)
        self.assertEqual(segundo_titular.mesa_id, self.mesa.pk)
        self.assertEqual(AsignacionMesa.objects.get(registro_padron=self.registros[1]).mesa_id, self.mesa.pk)
        self.assertEqual(AsignacionAutoridad.objects.filter(mesa=otra, tipo="titular").count(), 1)

    def test_cupos_insuficientes_no_eliminan_asignaciones(self):
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=2, suplentes_por_mesa=0)
        primera = asignar_manualmente(self.mesa, self.manana, self.registros[0], self.usuario, tipo="titular")
        segunda = asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="titular")
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1)
        respuesta = self.cargar([self.registros[2].elector.dni])
        self.assertContains(respuesta, "No se pueden conservar todas las asignaciones existentes")
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", flat=True)), {primera.pk, segunda.pk})
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")

    def test_aumentar_cupos_previsualiza_y_conserva_designaciones(self):
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=1)
        self.cargar()
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id", "turno_id", "tipo"))
        respuesta = self.client.post(self.ruta, {
            "guardar-turnos": "1", "configuracion-turnos": [self.manana.pk],
            f"titulares_{self.manana.pk}": "2",
        }, follow=True)
        self.assertContains(respuesta, "Revisar distribución propuesta")
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id", "turno_id", "tipo")), anteriores)
        self.client.post(self.ruta, {"confirmar-nomina": "1"})
        self.assertTrue(anteriores.issubset(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "mesa_id", "turno_id", "tipo"))))
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)

    def test_guardar_turnos_sin_mesas_no_exige_previsualizacion(self):
        from apps.mesas.models import AsignacionMesa
        self.opciones.modo = "nomina"
        self.opciones.save()
        CandidaturaAutoridad.objects.create(registro_padron=self.registros[0], cargada_por=self.usuario)
        AsignacionMesa.objects.filter(mesa=self.mesa).delete()
        self.mesa.delete()
        respuesta = self.client.post(self.ruta, {
            "guardar-turnos": "1", "configuracion-turnos": [self.manana.pk],
            f"titulares_{self.manana.pk}": "2", f"suplentes_{self.manana.pk}": "0",
        }, follow=True)
        self.assertContains(respuesta, "Configurá mesas y turnos")
        self.assertEqual(self.eleccion_claustro.turnos_autoridad.get(turno=self.manana).titulares_por_mesa, 2)
        self.assertNotContains(respuesta, "Revisar distribución propuesta")

    def test_editar_mesa_disponible_en_todos_los_modos(self):
        ruta_mesa = reverse("seleccionar-autoridades-mesa", args=(self.eleccion.pk, self.eleccion_claustro.pk, self.mesa.pk))
        for modo in ("aleatorio", "nomina", "manual"):
            with self.subTest(modo=modo):
                self.opciones.modo = modo
                self.opciones.save()
                pagina = self.client.get(self.ruta)
                self.assertContains(pagina, "Editar mesa")
                self.assertNotContains(pagina, '<option value="manual">', html=True)
                self.assertEqual(self.client.get(ruta_mesa).status_code, 200)

    def test_agregar_y_quitar_manualmente_en_cualquier_modo(self):
        ruta = reverse("seleccionar-autoridades-mesa", args=(self.eleccion.pk, self.eleccion_claustro.pk, self.mesa.pk))
        for modo in ("aleatorio", "nomina", "manual"):
            with self.subTest(modo=modo):
                self.opciones.modo = modo
                self.opciones.save()
                respuesta = self.client.post(ruta, {
                    "seleccionar": "1", "turno": self.manana.pk,
                    "tipo": "titular", "registro": self.registros[0].pk,
                }, follow=True)
                self.assertContains(respuesta, "Designación guardada")
                asignacion = AsignacionAutoridad.objects.get(registro_padron=self.registros[0])
                self.client.post(ruta, {"quitar-asignacion": str(asignacion.pk)})
                self.assertFalse(AsignacionAutoridad.objects.filter(pk=asignacion.pk).exists())

    def test_modo_planilla_retirado_no_cambia_asignaciones(self):
        anterior = asignar_manualmente(self.mesa, self.manana, self.registros[0], self.usuario, tipo="titular")
        r = self.registros[0]
        contenido = ("Mesa,Tipo documento,Documento,Legajo,Turno,Funcion,Orden\n"
                     f"{self.mesa.codigo},DNI,{r.elector.dni},{r.elector.legajo},{self.manana.nombre},suplente,1\n")
        respuesta = self.client.post(self.ruta, {
            "aplicar-modo": "1", "modo": "planilla",
            "archivo": SimpleUploadedFile("seleccion.csv", contenido.encode()),
        }, follow=True)
        self.assertNotContains(respuesta, '<option value="planilla">')
        anterior.refresh_from_db()
        self.assertEqual((anterior.tipo, anterior.mesa_id, anterior.turno_id), ("titular", self.mesa.pk, self.manana.pk))

    def test_destinos_de_nomina_respetan_opciones_y_sede_de_cursada(self):
        from apps.autoridades.distribucion import _puede_trabajar_nomina, _registros
        from apps.mesas.models import Mesa
        otra_mesa = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion,
                                       eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        otra_sede = Mesa.objects.create(eleccion=self.eleccion, numero=3, sede=self.sede,
                                       eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        registro = _registros(self.eleccion_claustro).get(pk=self.registros[0].pk)
        self.opciones.modo = "nomina"
        self.assertTrue(_puede_trabajar_nomina(registro, self.mesa, self.manana, self.opciones))
        self.assertFalse(_puede_trabajar_nomina(registro, otra_mesa, self.manana, self.opciones))
        self.assertFalse(_puede_trabajar_nomina(registro, otra_sede, self.manana, self.opciones))
        self.opciones.permitir_mesa_distinta = True
        self.assertTrue(_puede_trabajar_nomina(registro, otra_mesa, self.manana, self.opciones))
        self.assertFalse(_puede_trabajar_nomina(registro, otra_sede, self.manana, self.opciones))
        self.opciones.permitir_mesa_distinta = False
        self.opciones.reacomodar_titulares = True
        self.assertTrue(_puede_trabajar_nomina(registro, otra_mesa, self.manana, self.opciones))
        self.opciones.permitir_cambio_sede = True
        self.assertTrue(_puede_trabajar_nomina(registro, otra_sede, self.manana, self.opciones))
        registro.sede = self.sede_votacion
        self.assertFalse(_puede_trabajar_nomina(registro, otra_sede, self.manana, self.opciones))

    def test_error_en_archivo_revierte_modo_opciones_y_nomina(self):
        respuesta = self.cargar([self.registros[0].elector.dni, "INEXISTENTE"], permitir_cambio_sede="on", reacomodar_titulares="on")
        self.assertContains(respuesta, "no pertenece al padron activo")
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")
        self.assertFalse(self.opciones.permitir_cambio_sede)
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_error_distribucion_revierte_importacion_completa(self):
        with patch("apps.autoridades.nomina.distribuir", side_effect=ValidationError("Sin capacidad")):
            respuesta = self.cargar()
        self.assertContains(respuesta, "Sin capacidad")
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")

    def test_archivo_obligatorio_no_cambia_modo(self):
        respuesta = self.client.post(self.ruta, {"modo": "nomina", "aplicar-modo": "1"})
        self.assertTrue(respuesta.context["formulario_nomina"].errors)
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")

    def test_qr_bloquea_carga_y_opciones(self):
        self.registros[0].qr_generado_en = timezone.now()
        self.registros[0].save(update_fields=("qr_generado_en",))
        self.cargar()
        self.client.post(self.ruta, {"actualizar-nomina": "1", "modo": "nomina", "permitir_cambio_sede": "on"})
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")
        self.assertFalse(CandidaturaAutoridad.objects.exists())

    def test_plantilla_nomina_no_pide_destinos(self):
        ruta = reverse("descargar-plantilla-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        respuesta = self.client.get(ruta, {"modo": "nomina"})
        self.assertEqual(respuesta.content.decode("utf-8-sig").strip(), "Tipo documento,Documento,Legajo")
