from django.core.exceptions import ValidationError
from itertools import product
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.autoridades.distribucion import _completar_plazas, _optimizar_nomina, distribuir, guardar_selecciones
from apps.autoridades.forms import FormularioSeleccionMesa
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, ConfiguracionAutoridades
from apps.autoridades.seleccion_manual import asignar_manualmente
from apps.autoridades import tests as casos_base
from apps.elecciones.models import EleccionClaustroTurno
from apps.mesas.models import AsignacionMesa, Mesa
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.justificativos.services import resolver_justificativo


class CoberturaOptimaTests(SimpleTestCase):
    def test_nomina_maximiza_cobertura_y_prioriza_mesa_y_sede_globalmente(self):
        niveles = [0, 1, 2]
        for mascara in range(1 << 9):
            candidatos = [[(p, (p + plaza) % 3) for p in range(3) if mascara & (1 << (plaza * 3 + p))] for plaza in range(3)]
            def calidad(asignacion):
                distancias = [dict(candidatos[i])[p] for i, p in asignacion.items()]
                return (len(asignacion), int(0 in asignacion), int(1 in asignacion), distancias.count(0), distancias.count(1))
            mejor = (0, 0, 0, 0, 0)
            for opcion in product(*[[-1, *[p for p, _ in fila]] for fila in candidatos]):
                personas = [p for p in opcion if p != -1]
                if len(personas) != len(set(personas)):
                    continue
                mejor = max(mejor, calidad({i: p for i, p in enumerate(opcion) if p != -1}))
            resultado = _optimizar_nomina(candidatos, niveles, {})
            self.assertEqual(calidad(resultado), mejor, candidatos)

    def test_nomina_conserva_cupo_fijo_aunque_otra_combinacion_tenga_menos_movimientos(self):
        candidatos = [[(1, 1), (2, 0)], [(1, 0), (2, 1)]]
        resultado = _optimizar_nomina(candidatos, [0, 0], {0: 1})
        self.assertEqual(resultado, {0: 1, 1: 2})

    def test_cobertura_coincide_con_busqueda_exhaustiva_en_grafos_pequenos(self):
        # Dos titulares antes de un suplente; cada grafo representa distintas
        # compatibilidades horarias. El oráculo enumera todas las asignaciones.
        for mascara in range(1 << 9):
            candidatos = [[p for p in range(3) if mascara & (1 << (plaza * 3 + p))] for plaza in range(3)]
            for fijas in [{}, *({0: p} for p in candidatos[0])]:
                def calidad(asignacion):
                    return (int(0 in asignacion), sum(p < 2 for p in asignacion), len(asignacion))

                mejor = (0, 0, 0)
                for opcion in product(*[[-1, *personas] for personas in candidatos]):
                    elegidas = [p for p in opcion if p != -1]
                    if len(elegidas) != len(set(elegidas)) or any(opcion[i] != p for i, p in fijas.items()):
                        continue
                    mejor = max(mejor, calidad({i: p for i, p in enumerate(opcion) if p != -1}))
                resultado = _completar_plazas(candidatos, fijas)
                self.assertEqual(calidad(resultado), mejor, (candidatos, fijas, resultado))
                self.assertEqual(len(resultado), len(set(resultado.values())))
                self.assertTrue(all(p in candidatos[i] for i, p in resultado.items()))
                self.assertTrue(all(resultado[i] == p for i, p in fijas.items()))

    def test_reorganiza_cadena_larga_sin_limite_de_recursion(self):
        cantidad = 1100
        candidatos = [[i, i + 1] for i in range(cantidad)] + [[0]]
        resultado = _completar_plazas(candidatos, {})
        self.assertEqual(len(resultado), cantidad + 1)
        self.assertEqual(len(set(resultado.values())), cantidad + 1)
        self.assertEqual(resultado[cantidad], 0)


class DistribucionAutoridadesTests(TestCase):
    def setUp(self):
        casos_base.TurnosAutoridadesTests.setUp(self)
        self.opciones = ConfiguracionAutoridades.objects.create(eleccion_claustro=self.eleccion_claustro)

    def nomina(self):
        for r in self.registros:
            CandidaturaAutoridad.objects.get_or_create(registro_padron=r, defaults={"cargada_por": self.usuario})

    def cupos(self, titulares=1, suplentes=1):
        self.eleccion_claustro.turnos_autoridad.update(titulares_por_mesa=titulares, suplentes_por_mesa=suplentes)

    def test_nomina_comun_visible_con_carga_y_opciones(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk)))
        self.assertContains(respuesta, '<option value="nomina" selected>Nómina común</option>', html=True)
        self.assertContains(respuesta, 'name="permitir_cambio_sede"')
        self.assertContains(respuesta, 'name="reacomodar_titulares"')
        self.assertContains(respuesta, 'name="permitir_mesa_distinta"')
        self.assertNotContains(respuesta, 'name="agregar-candidato"')
        self.assertContains(respuesta, 'name="archivo"')
        self.assertContains(respuesta, "Previsualizar nómina")
        self.assertNotContains(respuesta, "Cargar desde planilla")
        self.assertEqual(respuesta.context["modo_vista"], "nomina")

    def test_volver_a_nomina_guarda_opciones_y_distribuye(self):
        self.nomina()
        self.cupos(titulares=1, suplentes=0)
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.client.force_login(self.usuario)
        ruta = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        from django.core.files.uploadedfile import SimpleUploadedFile
        archivo = SimpleUploadedFile("nomina.csv", ("Documento\n" + self.registros[0].elector.dni + "\n").encode())
        respuesta = self.client.post(ruta, {
            "aplicar-modo": "1", "modo": "nomina",
            "archivo": archivo,
            "permitir_cambio_sede": "on", "reacomodar_titulares": "on",
        }, follow=True)
        self.assertContains(respuesta, "Revisar distribución propuesta")
        respuesta = self.client.post(ruta, {"confirmar-nomina": "1"}, follow=True)
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "nomina")
        self.assertTrue(self.opciones.permitir_cambio_sede)
        self.assertTrue(self.opciones.reacomodar_titulares)
        self.assertFalse(self.opciones.permitir_mesa_distinta)
        self.assertTrue(AsignacionAutoridad.objects.exists())
        self.assertEqual(respuesta.context["modo_vista"], "nomina")
        self.client.post(ruta, {"actualizar-nomina": "1", "modo": "nomina"})
        self.client.post(ruta, {"confirmar-nomina": "1"})
        self.opciones.refresh_from_db()
        self.assertFalse(self.opciones.permitir_cambio_sede)
        self.assertFalse(self.opciones.reacomodar_titulares)
        self.assertFalse(self.opciones.permitir_mesa_distinta)

    def test_planilla_no_figura_como_modalidad(self):
        from apps.autoridades.forms import FormularioConfiguracionAutoridades
        formulario = FormularioConfiguracionAutoridades(
            {"modo": "planilla", "permitir_mesa_distinta": "", "permitir_cambio_sede": ""},
            instance=self.opciones,
        )
        self.assertFalse(formulario.is_valid())
        self.assertNotIn(("planilla", "Cargar desde planilla"), formulario.fields["modo"].choices)

    def test_modo_manual_anterior_abre_la_tabla_sin_modificar_asignaciones(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        distribuir(self.eleccion_claustro, self.usuario)
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "tipo"))
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("gestionar-autoridades-claustro", args=(self.eleccion.id, self.eleccion_claustro.id)),
            {"aplicar-modo": "", "modo": "manual"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.endswith("#asignaciones"))
        pagina_manual = self.client.get(respuesta.url)
        self.assertContains(pagina_manual, 'name="aplicar-modo"')
        self.assertNotContains(pagina_manual, '<option value="manual">', html=True)
        self.assertContains(pagina_manual, "Editar mesa")
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "tipo")), anteriores)
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")

    def test_formulario_manual_solo_muestra_personas_disponibles_y_no_tiene_archivo(self):
        self.cupos(titulares=2, suplentes=0)
        asignar_manualmente(self.mesa, self.manana, self.registros[0], self.usuario, tipo="titular")
        excluida = CandidaturaAutoridad.objects.create(registro_padron=self.registros[1], cargada_por=self.usuario, excluida=True)

        formulario = FormularioSeleccionMesa(mesa=self.mesa, initial={"turno": self.manana.pk})

        ids = set(formulario.fields["registro"].queryset.values_list("pk", flat=True))
        self.assertEqual(ids, {self.registros[2].pk})
        self.assertNotIn("archivo", formulario.fields)
        self.assertNotIn(excluida.registro_padron_id, ids)

    def test_reemplazar_cupo_manual_modifica_solo_la_mesa_y_el_cupo_elegidos(self):
        self.cupos(titulares=2, suplentes=0)
        anterior = asignar_manualmente(self.mesa, self.manana, self.registros[0], self.usuario, tipo="titular")
        asignacion_ajena = asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="titular")

        nueva = asignar_manualmente(
            self.mesa, self.manana, self.registros[2], self.usuario,
            tipo="titular", reemplazar=anterior,
        )

        self.assertFalse(AsignacionAutoridad.objects.filter(pk=anterior.pk).exists())
        self.assertTrue(AsignacionAutoridad.objects.filter(pk=asignacion_ajena.pk).exists())
        self.assertEqual(AsignacionAutoridad.objects.get(registro_padron=self.registros[2]).pk, nueva.pk)
        self.assertEqual(AsignacionAutoridad.objects.filter(mesa=self.mesa, tipo="titular").count(), 2)

    def test_todos_los_turnos_titulares_antes_de_cualquier_suplente(self):
        self.nomina()
        self.cupos(2, 1)
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.tarde, titulares_por_mesa=1, suplentes_por_mesa=1)
        r = self.registros[2]
        r.turno_cursada = self.manana
        r.save()
        distribuir(self.eleccion_claustro, self.usuario)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 3)
        self.assertFalse(AsignacionAutoridad.objects.filter(tipo="suplente").exists())

    def test_reubica_persona_flexible_para_no_dejar_otro_turno_sin_titular(self):
        self.nomina()
        self.cupos(2, 0)
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.tarde, titulares_por_mesa=1)
        r = self.registros[0]
        r.sede = None
        r.turno_cursada = None
        r.save()
        resultado = distribuir(self.eleccion_claustro, self.usuario)
        self.assertEqual(resultado["titulares_faltantes"], 0)
        self.assertEqual(AsignacionAutoridad.objects.get(registro_padron=r).turno, self.tarde)

    def test_sorteo_usa_padron_sin_cargar_nomina_y_respeta_cupos(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos()
        distribuir(self.eleccion_claustro, self.usuario)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 1)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="suplente").count(), 1)
        self.assertEqual(CandidaturaAutoridad.objects.count(), 2)

    def test_repetir_sorteo_conserva_dos_titulares_distintos(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos(2, 1)
        distribuir(self.eleccion_claustro, self.usuario)
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "tipo"))
        resultado = distribuir(self.eleccion_claustro, self.usuario)
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id", "tipo")), anteriores)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)
        self.assertEqual(resultado["conservadas"], 3)
        self.assertEqual(resultado["asignadas"], 3)
        self.assertEqual(resultado["titulares_faltantes"], 0)

    def test_aumentar_cupos_conserva_titular_y_asigna_otra_persona(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos(1, 0)
        distribuir(self.eleccion_claustro, self.usuario)
        anterior = AsignacionAutoridad.objects.get()
        self.cupos(2, 0)
        resultado = distribuir(self.eleccion_claustro, self.usuario)
        self.assertTrue(AsignacionAutoridad.objects.filter(pk=anterior.pk).exists())
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)
        self.assertEqual(resultado["conservadas"], 1)
        self.assertEqual(resultado["nuevas"], 1)
        self.assertEqual(resultado["titulares_faltantes"], 0)

    def test_sorteo_no_toma_electores_de_otra_mesa(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        otra = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion, eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        resultado = distribuir(self.eleccion_claustro, self.usuario)
        self.assertFalse(otra.autoridades.exists())
        self.assertEqual(resultado["titulares_faltantes"], 2)

    def test_recalcular_reemplaza_todas_las_asignaciones_y_limpia_destinos(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos(2, 1)
        distribuir(self.eleccion_claustro, self.usuario)
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", flat=True))
        CandidaturaAutoridad.objects.update(
            mesa_manual=self.mesa, turno_manual=self.manana, tipo_manual="suplente", orden_manual=1,
            mesa_traslado=self.mesa, turno_traslado=self.tarde,
        )
        # Una llamada directa al servicio debe tener las mismas garantías que el botón.
        resultado = distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
        self.assertFalse(AsignacionAutoridad.objects.filter(pk__in=anteriores).exists())
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 2)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="suplente").count(), 1)
        self.assertEqual(resultado["conservadas"], 0)
        self.assertEqual(resultado["titulares_faltantes"], 0)
        self.assertFalse(CandidaturaAutoridad.objects.exclude(mesa_manual=None, mesa_traslado=None).exists())
        from apps.auditoria.models import EventoAuditoria
        evento = EventoAuditoria.objects.filter(accion="autoridades.distribuidas").latest("pk")
        self.assertEqual(evento.datos_nuevos["operacion"], "recalcular")
        self.assertEqual(len(evento.datos_nuevos["asignaciones_resultantes"]), 3)

    def test_recalculo_fallido_revierte_asignaciones_y_selecciones(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos()
        distribuir(self.eleccion_claustro, self.usuario)
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id"))
        candidatura = CandidaturaAutoridad.objects.first()
        candidatura.mesa_manual = self.mesa
        candidatura.turno_manual = self.manana
        candidatura.tipo_manual = "titular"
        candidatura.save()
        with patch("apps.autoridades.distribucion.AsignacionAutoridad.objects.bulk_create", side_effect=ValidationError("Fallo de guardado")):
            with self.assertRaisesMessage(ValidationError, "Fallo de guardado"):
                distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("pk", "registro_padron_id")), anteriores)
        candidatura.refresh_from_db()
        self.assertEqual(candidatura.mesa_manual_id, self.mesa.pk)

    def test_recalcular_puede_volver_a_elegir_las_mismas_personas(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos()
        with patch("apps.autoridades.distribucion.SystemRandom"):
            distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
            personas = set(AsignacionAutoridad.objects.values_list("registro_padron_id", "tipo"))
            ids = set(AsignacionAutoridad.objects.values_list("pk", flat=True))
            distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
        self.assertEqual(set(AsignacionAutoridad.objects.values_list("registro_padron_id", "tipo")), personas)
        self.assertFalse(AsignacionAutoridad.objects.filter(pk__in=ids).exists())

    def test_azar_desempata_turnos_de_igual_prioridad_si_no_alcanza_el_padron(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos(1, 0)
        EleccionClaustroTurno.objects.create(
            eleccion_claustro=self.eleccion_claustro, turno=self.tarde,
            titulares_por_mesa=1, suplentes_por_mesa=0,
        )
        self.nomina()
        CandidaturaAutoridad.objects.exclude(registro_padron=self.registros[0]).update(excluida=True)
        registro = self.registros[0]
        registro.sede = None
        registro.turno_cursada = None
        registro.save()
        with patch("apps.autoridades.distribucion.SystemRandom") as azar:
            distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
            primero = AsignacionAutoridad.objects.get().turno_id
            azar.return_value.shuffle.side_effect = lambda elementos: elementos.reverse()
            resultado = distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
            segundo = AsignacionAutoridad.objects.get().turno_id
        self.assertEqual({primero, segundo}, {self.manana.pk, self.tarde.pk})
        self.assertEqual(resultado["titulares_faltantes"], 1)

    def test_aplicar_conserva_selecciones_manual_y_suplente_con_vacante_titular(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos()
        distribuir(self.eleccion_claustro, self.usuario)
        suplente = AsignacionAutoridad.objects.get(tipo="suplente")
        candidatura = suplente.candidatura
        candidatura.mesa_manual = self.mesa
        candidatura.turno_manual = self.manana
        candidatura.tipo_manual = "suplente"
        candidatura.orden_manual = 1
        candidatura.save()
        anteriores = set(AsignacionAutoridad.objects.values_list("pk", flat=True))
        self.cupos(3, 1)
        self.client.force_login(self.usuario)
        ruta = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        respuesta = self.client.post(ruta, {"aplicar-modo": "1", "modo": "aleatorio"}, follow=True)
        self.assertContains(respuesta, "conservando las asignaciones")
        self.assertEqual(AsignacionAutoridad.objects.filter(pk__in=anteriores).count(), 2)
        suplente.refresh_from_db()
        candidatura.refresh_from_db()
        self.assertEqual(suplente.tipo, "suplente")
        self.assertEqual(candidatura.mesa_manual_id, self.mesa.pk)
        # Recalcular sí puede usar ese suplente para completar los titulares.
        respuesta = self.client.post(ruta, {"recalcular-distribucion": "1"}, follow=True)
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="titular").count(), 3)
        self.assertFalse(AsignacionAutoridad.objects.filter(tipo="suplente").exists())
        self.assertContains(respuesta, "Faltan 0 titulares y 1 suplentes")

    def test_recalculo_respeta_exclusiones_y_no_toca_el_padron(self):
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.cupos(2, 1)
        self.nomina()
        CandidaturaAutoridad.objects.filter(registro_padron=self.registros[0]).update(excluida=True)
        ubicaciones = list(AsignacionMesa.objects.values_list("pk", "mesa_id", "registro_padron_id"))
        resultado = distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
        self.assertFalse(AsignacionAutoridad.objects.filter(registro_padron=self.registros[0]).exists())
        self.assertEqual(resultado["titulares_faltantes"], 0)
        self.assertEqual(resultado["suplentes_faltantes"], 1)
        self.assertEqual(list(AsignacionMesa.objects.values_list("pk", "mesa_id", "registro_padron_id")), ubicaciones)

    def test_recalculo_rechaza_modo_manual_y_qr_sin_limpiar_selecciones(self):
        self.nomina()
        candidatura = CandidaturaAutoridad.objects.first()
        candidatura.mesa_manual = self.mesa
        candidatura.turno_manual = self.manana
        candidatura.tipo_manual = "titular"
        candidatura.save()
        self.opciones.modo = "manual"
        self.opciones.save()
        with self.assertRaisesMessage(ValidationError, "requiere el modo"):
            distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        self.registros[0].qr_generado_en = timezone.now()
        self.registros[0].save()
        with self.assertRaisesMessage(ValidationError, "imprimible"):
            distribuir(self.eleccion_claustro, self.usuario, preservar_asignaciones=False)
        candidatura.refresh_from_db()
        self.assertEqual(candidatura.mesa_manual_id, self.mesa.pk)

    def test_seleccion_manual_valida_cupos_y_revierte_lote_invalido(self):
        self.opciones.modo = "manual"
        self.opciones.save()
        self.cupos()
        filas = [(r, self.mesa, self.manana, "titular", None) for r in self.registros[:2]]
        with self.assertRaisesMessage(ValidationError, "cupo"):
            guardar_selecciones(self.eleccion_claustro, filas, self.usuario)
        self.assertFalse(CandidaturaAutoridad.objects.exists())
        guardar_selecciones(self.eleccion_claustro, filas[:1], self.usuario)
        self.assertEqual(AsignacionAutoridad.objects.get().registro_padron, self.registros[0])

    def test_mesa_distinta_no_mueve_el_padron_de_votacion(self):
        self.cupos(titulares=1, suplentes=0)
        otra = Mesa.objects.create(eleccion=self.eleccion, numero=2, sede=self.sede_votacion, eleccion_claustro_departamento=self.mesa.eleccion_claustro_departamento)
        from apps.autoridades.seleccion_manual import asignar_manualmente
        asignar_manualmente(self.mesa, self.manana, self.registros[1], self.usuario, tipo="titular")
        nominada = self.registros[0]
        CandidaturaAutoridad.objects.create(registro_padron=nominada, cargada_por=self.usuario)
        ubicaciones_previas = list(AsignacionMesa.objects.order_by("registro_padron_id").values_list("registro_padron_id", "mesa_id", "autoridad_al_final"))
        self.opciones.modo = "nomina"
        self.opciones.permitir_mesa_distinta = True
        self.opciones.save()
        distribuir(self.eleccion_claustro, self.usuario)
        asignacion = AsignacionAutoridad.objects.get(registro_padron=nominada)
        self.assertEqual(asignacion.mesa_id, otra.pk)
        self.assertEqual(list(AsignacionMesa.objects.order_by("registro_padron_id").values_list("registro_padron_id", "mesa_id", "autoridad_al_final")), ubicaciones_previas)

    def test_qr_bloquea_distribucion_y_seleccion(self):
        r = self.registros[0]
        r.qr_generado_en = timezone.now()
        r.numero_mesa_qr = self.mesa.numero
        r.save()
        with self.assertRaisesMessage(ValidationError, "imprimible"):
            distribuir(self.eleccion_claustro, self.usuario)
        self.assertFalse(AsignacionAutoridad.objects.exists())

    def test_confirmacion_junta_promueve_una_sola_vez_y_conserva_qr(self):
        from apps.autoridades.services import responder_asignacion
        from apps.autoridades.reemplazos import confirmar_reemplazo
        self.nomina()
        self.cupos(1, 2)
        distribuir(self.eleccion_claustro, self.usuario)
        titular = AsignacionAutoridad.objects.get(tipo="titular")
        suplente = AsignacionAutoridad.objects.get(tipo="suplente", orden_suplencia=1)
        justificativo = JustificativoAusencia.objects.create(registro_padron=titular.registro_padron, ausencia="autoridad", tipo=TipoJustificativo.objects.create(nombre="Salud"), detalle="Prueba")
        r = suplente.registro_padron
        r.qr_generado_en = timezone.now()
        r.numero_mesa_qr = self.mesa.numero
        r.save()
        responder_asignacion(titular)
        for _ in range(2):
            resolver_justificativo(justificativo, estado="aprobado", observacion="", usuario=self.usuario)
            confirmar_reemplazo(titular, self.usuario)
        titular.refresh_from_db()
        suplente.refresh_from_db()
        self.assertEqual(titular.estado, "rechazada")
        self.assertEqual(suplente.tipo, "titular")
        self.assertEqual(AsignacionAutoridad.objects.filter(tipo="suplente", orden_suplencia=1).count(), 1)
        self.assertEqual(r.asignacion_mesa.mesa_id, self.mesa.pk)

    def test_justificativo_rechazado_no_cambia_autoridades(self):
        self.nomina()
        self.cupos()
        distribuir(self.eleccion_claustro, self.usuario)
        titular = AsignacionAutoridad.objects.get(tipo="titular")
        j = JustificativoAusencia.objects.create(registro_padron=titular.registro_padron, ausencia="autoridad", tipo=TipoJustificativo.objects.create(nombre="Salud"), detalle="Prueba")
        resolver_justificativo(j, estado="rechazado", observacion="", usuario=self.usuario)
        titular.refresh_from_db()
        self.assertEqual(titular.estado, "asignada")

    def test_pantalla_manual_y_exportacion_por_mesa(self):
        self.opciones.modo = "manual"
        self.opciones.save()
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("seleccionar-autoridades-mesa", args=(self.eleccion.pk, self.eleccion_claustro.pk, self.mesa.pk)))
        self.assertContains(respuesta, "Persona disponible de la mesa")
        self.assertNotContains(respuesta, 'type="file"')
        respuesta = self.client.get(reverse("descargar-plantilla-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk)))
        self.assertContains(respuesta, "Tipo documento,Documento,Legajo")

    def crear_candidatura_electoral(self, registro):
        from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido
        presentacion = ParticipacionPartido.objects.create(eleccion=self.eleccion, eleccion_claustro=self.eleccion_claustro, numero_lista="1")
        lista = ListaCandidatos.objects.create(participacion=presentacion, eleccion_claustro=self.eleccion_claustro, nombre="Lista")
        return Candidato.objects.create(lista=lista, elector=registro.elector, dni=registro.elector.dni, nombre=registro.elector.nombre_completo, cargo="Consejero", orden=1)

    def test_candidato_electoral_excluido_del_sorteo_y_csv(self):
        from apps.autoridades.services import validar_csv_autoridades
        self.crear_candidatura_electoral(self.registros[0])
        self.opciones.modo = "aleatorio"
        self.opciones.save()
        distribuir(self.eleccion_claustro, self.usuario)
        self.assertFalse(AsignacionAutoridad.objects.filter(registro_padron=self.registros[0]).exists())
        _, errores = validar_csv_autoridades(f"Documento\n{self.registros[0].elector.dni}\n".encode(), self.eleccion_claustro)
        self.assertTrue(any("candidato electoral" in mensaje for _, mensaje in errores))

    def test_candidato_electoral_rechazado_en_seleccion_manual(self):
        self.crear_candidatura_electoral(self.registros[0])
        self.opciones.modo = "manual"
        self.opciones.save()
        with self.assertRaisesMessage(ValidationError, "elegible"):
            guardar_selecciones(self.eleccion_claustro, [(self.registros[0], self.mesa, self.manana, "titular", None)], self.usuario)

    def test_cambio_sede_deshabilitado_y_proteccion_de_sede_de_cursada(self):
        from apps.autoridades.services import confirmar_cambio_sede_para_autoridad
        with self.assertRaisesMessage(ValidationError, "habilitados"):
            confirmar_cambio_sede_para_autoridad(self.registros[0], self.sede, self.usuario)
        self.opciones.permitir_cambio_sede = True
        self.opciones.save()
        r = self.registros[0]
        r.sede = self.sede_votacion
        r.save()
        with self.assertRaisesMessage(ValidationError, "origen"):
            confirmar_cambio_sede_para_autoridad(r, self.sede, self.usuario)

    def test_configurar_sorteo_se_aplica_y_qr_impide_cambiar_modo(self):
        self.client.force_login(self.usuario)
        ruta = reverse("gestionar-autoridades-claustro", args=(self.eleccion.pk, self.eleccion_claustro.pk))
        self.client.post(ruta, {"aplicar-modo": "1", "modo": "aleatorio"})
        self.assertEqual(AsignacionAutoridad.objects.count(), 2)
        r = self.registros[0]
        r.qr_generado_en = timezone.now()
        r.numero_mesa_qr = self.mesa.numero
        r.save()
        self.client.post(ruta, {"aplicar-modo": "1", "modo": "manual"})
        self.opciones.refresh_from_db()
        self.assertEqual(self.opciones.modo, "aleatorio")

    def test_pdf_ubica_bloque_final_despues_del_orden_alfabetico(self):
        from apps.reportes.services_pdf import _agrupar_padrones_por_mesa
        AsignacionMesa.objects.filter(registro_padron=self.registros[0]).update(autoridad_al_final=True)
        grupos = _agrupar_padrones_por_mesa(self.eleccion)
        self.assertEqual(grupos[0]["padrones"][-1].pk, self.registros[0].pk)

    def test_manual_no_permite_suplente_antes_de_completar_titulares(self):
        self.opciones.modo = "manual"
        self.opciones.save()
        self.cupos()
        with self.assertRaisesMessage(ValidationError, "Primero completá"):
            guardar_selecciones(self.eleccion_claustro, [(self.registros[0], self.mesa, self.manana, "suplente", 1)], self.usuario)
        self.assertFalse(CandidaturaAutoridad.objects.exists())

    def test_no_reactiva_candidatura_electoral_de_una_autoridad(self):
        candidato = self.crear_candidatura_electoral(self.registros[0])
        candidato.activo = False
        candidato.save()
        self.nomina()
        distribuir(self.eleccion_claustro, self.usuario)
        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse("cambiar-estado-candidato", args=(self.eleccion.pk, candidato.pk)), {"activo": "1"})
        self.assertEqual(respuesta.status_code, 302)
        candidato.refresh_from_db()
        self.assertFalse(candidato.activo)

    def test_sin_suplente_confirmacion_deja_vacante(self):
        from apps.autoridades.services import responder_asignacion
        from apps.autoridades.reemplazos import confirmar_reemplazo
        self.nomina()
        self.cupos(1, 0)
        distribuir(self.eleccion_claustro, self.usuario)
        titular = AsignacionAutoridad.objects.get()
        j = JustificativoAusencia.objects.create(registro_padron=titular.registro_padron, ausencia="autoridad", tipo=TipoJustificativo.objects.create(nombre="Salud"), detalle="Prueba")
        resolver_justificativo(j, estado="aprobado", observacion="", usuario=self.usuario)
        responder_asignacion(titular)
        confirmar_reemplazo(titular, self.usuario)
        self.assertFalse(AsignacionAutoridad.objects.filter(estado="asignada").exists())
