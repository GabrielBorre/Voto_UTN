from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.asistencia.dashboard import FiltrosDashboard, construir_dashboard
from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionSede
from apps.elecciones.views import MESAS_POR_PAGINA
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede
from apps.usuarios.models import AsignacionRol, PerfilUsuario


class DashboardParticipacionTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion Dashboard",
            fecha_inicio=date(2026, 8, 3),
            fecha_fin=date(2026, 8, 3),
            estado=Eleccion.Estado.EN_CURSO,
        )
        self.sede_a = Sede.objects.create(nombre="Sede A")
        self.sede_b = Sede.objects.create(nombre="Sede B")
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede_a)
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede_b)
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro, departamento=self.departamento
        )
        self.mesa_a = self.crear_mesa(1, self.sede_a)
        self.mesa_b = self.crear_mesa(2, self.sede_b)
        self.registros_a = [self.crear_registro(i, self.mesa_a, self.sede_a) for i in (1, 2)]
        self.registros_b = [self.crear_registro(i, self.mesa_b, self.sede_b) for i in (3, 4)]

        self.administrativo = get_user_model().objects.create_user(username="administrativo", password="clave")
        AsignacionRol.objects.create(
            usuario=self.administrativo, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion
        )

    def crear_mesa(self, numero, sede):
        return Mesa.objects.create(
            eleccion=self.eleccion, numero=numero, eleccion_claustro_departamento=self.configuracion, sede=sede
        )

    def crear_registro(self, indice, mesa, sede):
        elector = Elector.objects.create(
            legajo=f"L{indice}",
            nombre=f"Elector {indice}",
            dni=f"3000000{indice}",
            correo_electronico=f"elector{indice}@example.test",
        )
        registro = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion, eleccion_claustro_departamento=self.configuracion, sede=sede
        )
        AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
        return registro

    def registrar_participacion(self, registro, mesa):
        Mesa.objects.filter(pk=mesa.pk).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        return RegistroParticipacion.objects.create(
            registro_padron=registro, mesa=mesa, registrada_por=self.administrativo, metodo="qr"
        )

    def pendientes(self, datos):
        return [mesa.numero for mesa in datos["mesas"] if mesa.estado_escaneo != Mesa.EstadoEscaneo.PROCESADA]

    def test_calcula_porcentajes_y_mesas_pendientes(self):
        self.registrar_participacion(self.registros_a[0], self.mesa_a)

        datos = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())

        self.assertEqual((datos["mesas_total"], datos["mesas_escaneadas"], datos["mesas_escaneadas_pct"]), (2, 1, 50))
        self.assertEqual(self.pendientes(datos), [2])
        self.assertEqual([(m.cantidad_electores, m.cantidad_participaron) for m in datos["mesas"]], [(2, 1), (2, 0)])
        self.assertEqual(
            (datos["electores_total"], datos["electores_participaron"], datos["electores_participaron_pct"]),
            (4, 1, 50),
        )
        self.assertEqual(datos["electores_en_mesas_escaneadas"], 2)
        self.assertEqual(datos["historial"]["porcentajes"], [50])
        self.assertEqual(datos["historial"]["etiquetas"], ["Eleccion Dashboard"])

    def test_votaron_son_los_electores_sin_qr_escaneado_y_solo_en_mesas_procesadas(self):
        self.registrar_participacion(self.registros_a[0], self.mesa_a)
        Mesa.objects.filter(pk=self.mesa_a.pk).update(estado_escaneo=Mesa.EstadoEscaneo.EN_PROCESO)

        en_proceso = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())
        Mesa.objects.filter(pk=self.mesa_a.pk).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        procesada = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())

        self.client.force_login(self.administrativo)
        html = self.client.get(reverse("lista-elecciones"), {"eleccion": self.eleccion.pk}).content.decode()
        self.assertEqual(procesada["mesas"][0].cantidad_votaron, 1)
        self.assertEqual(en_proceso["mesas"][0].estado_escaneo, Mesa.EstadoEscaneo.EN_PROCESO)
        self.assertIn("<td>1</td>", html)

    def test_filtra_por_sede_claustro_y_departamento(self):
        self.registrar_participacion(self.registros_a[0], self.mesa_a)

        por_sede = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard(sede_id=self.sede_b.id))
        self.assertEqual((por_sede["electores_total"], por_sede["electores_participaron"]), (2, 0))
        self.assertEqual(self.pendientes(por_sede), [2])

        coincide = FiltrosDashboard(claustro_id=self.claustro.id, departamento_id=self.departamento.id)
        self.assertEqual(construir_dashboard(self.administrativo, self.eleccion, coincide)["electores_total"], 4)

        otro_claustro = Claustro.objects.create(nombre="Docentes")
        vacio = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard(claustro_id=otro_claustro.id))
        self.assertEqual((vacio["electores_total"], vacio["mesas_total"], vacio["electores_participaron_pct"]), (0, 0, 0))

    def test_ignora_electores_inactivos(self):
        RegistroPadron.objects.filter(pk=self.registros_b[0].pk).update(activo=False)

        datos = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())

        self.assertEqual(datos["electores_total"], 3)

    def test_alcance_por_sede_no_expone_mesas_ajenas(self):
        limitado = get_user_model().objects.create_user(username="limitado", password="clave")
        AsignacionRol.objects.create(
            usuario=limitado, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=self.eleccion, sede=self.sede_a
        )

        datos = construir_dashboard(limitado, self.eleccion, FiltrosDashboard())

        self.assertEqual(datos["mesas_total"], 1)
        self.assertEqual(self.pendientes(datos), [1])
        self.assertEqual(datos["electores_total"], 2)

    def test_filtro_de_estado_solo_acota_la_tabla_de_mesas(self):
        self.registrar_participacion(self.registros_a[0], self.mesa_a)

        escaneadas = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard(escaneo="procesada"))
        sin_escanear = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard(escaneo="pendiente"))

        self.assertEqual([mesa.numero for mesa in escaneadas["mesas"]], [1])
        self.assertEqual([mesa.numero for mesa in sin_escanear["mesas"]], [2])
        self.assertEqual((escaneadas["mesas_total"], sin_escanear["mesas_escaneadas"]), (2, 1))
        self.assertEqual(FiltrosDashboard.desde_parametros({"escaneo": "cualquiera"}).escaneo, "")

    def test_metricas_de_justificativos_sobre_ausentes_de_mesas_procesadas(self):
        tipo = TipoJustificativo.objects.create(nombre="Salud")
        self.registrar_participacion(self.registros_a[0], self.mesa_a)
        self.registrar_participacion(self.registros_a[1], self.mesa_a)
        self.crear_registro(5, self.mesa_a, self.sede_a)
        # Ausente = QR escaneado. Quien votó (QR retirado) o está en una mesa sin procesar no cuenta.
        JustificativoAusencia.objects.create(registro_padron=self.registros_b[0], tipo=tipo, detalle="x")
        justificativo = JustificativoAusencia.objects.create(registro_padron=self.registros_a[1], tipo=tipo, detalle="x")

        pendiente = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())
        self.assertEqual((pendiente["electores_ausentes"], pendiente["justificativos_recibidos"]), (2, 1))
        self.assertEqual((pendiente["electores_participaron"], pendiente["electores_en_mesas_escaneadas"]), (1, 3))
        self.assertEqual((pendiente["justificativos_recibidos_pct"], pendiente["justificativos_confirmados_pct"]), (50, 0))

        justificativo.estado = JustificativoAusencia.Estado.APROBADO
        justificativo.save()
        aprobado = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())
        self.assertEqual((aprobado["justificativos_confirmados"], aprobado["justificativos_confirmados_pct"]), (1, 100))

    def test_historial_compara_participacion_entre_elecciones(self):
        self.registrar_participacion(self.registros_a[0], self.mesa_a)
        anterior = Eleccion.objects.create(
            nombre="Eleccion Anterior",
            fecha_inicio=date(2025, 8, 3),
            fecha_fin=date(2025, 8, 3),
            estado=Eleccion.Estado.FINALIZADA,
            habilitada=False,
        )
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=anterior, claustro=self.claustro)
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro, departamento=self.departamento
        )
        mesa = Mesa.objects.create(eleccion=anterior, numero=1, eleccion_claustro_departamento=configuracion, sede=self.sede_a)
        elector = Elector.objects.create(legajo="OLD1", nombre="Elector Anterior", dni="30999999")
        registro = RegistroPadron.objects.create(
            elector=elector, eleccion=anterior, eleccion_claustro_departamento=configuracion, sede=self.sede_a
        )
        AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
        Mesa.objects.filter(pk=mesa.pk).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        AsignacionRol.objects.create(
            usuario=self.administrativo, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=anterior
        )

        historial = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())["historial"]

        self.assertEqual(historial["etiquetas"], ["Eleccion Anterior", "Eleccion Dashboard"])
        self.assertEqual(historial["porcentajes"], [100, 50])

    def test_vista_pagina_mesas_pendientes(self):
        for numero in range(3, 23):
            self.crear_mesa(numero, self.sede_a)
        self.client.force_login(self.administrativo)

        primera = self.client.get(reverse("lista-elecciones"))
        ultima = self.client.get(reverse("lista-elecciones"), {"pagina": 2})

        self.assertEqual(len(primera.context["pagina_mesas"].object_list), MESAS_POR_PAGINA)
        self.assertEqual(primera.context["pagina_mesas"].paginator.count, 22)
        self.assertEqual(ultima.context["pagina_mesas"].number, 2)

    def test_vista_muestra_tablero_con_filtros_y_carga_manual(self):
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(reverse("lista-elecciones"), {"sede": self.sede_b.id})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Estado de la mesa")
        self.assertContains(respuesta, "Justificativos recibidos")
        self.assertContains(respuesta, "Historial de participación")
        self.assertContains(respuesta, reverse("escanear", args=(self.eleccion.pk,)))
        self.assertEqual(respuesta.context["dashboard"]["electores_total"], 2)

    def test_vista_ignora_parametros_invalidos_y_elecciones_ajenas(self):
        ajena = Eleccion.objects.create(
            nombre="Ajena",
            fecha_inicio=date(2026, 9, 1),
            fecha_fin=date(2026, 9, 1),
            estado=Eleccion.Estado.FINALIZADA,
            habilitada=False,
        )
        administrador = get_user_model().objects.create_user(username="administrador", password="clave")
        AsignacionRol.objects.create(
            usuario=administrador, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse("lista-elecciones"), {"eleccion": ajena.id, "sede": "abc"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["eleccion_actual"], self.eleccion)
        self.assertEqual(respuesta.context["dashboard"]["electores_total"], 4)

    def test_registro_participacion_muestra_solo_la_eleccion_en_curso(self):
        finalizada = Eleccion.objects.create(
            nombre="Eleccion Finalizada Habilitada",
            fecha_inicio=date(2027, 8, 3),
            fecha_fin=date(2027, 8, 3),
            estado=Eleccion.Estado.FINALIZADA,
            habilitada=True,
        )
        AsignacionRol.objects.create(
            usuario=self.administrativo, rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA, eleccion=finalizada
        )
        self.client.force_login(self.administrativo)

        respuesta = self.client.get(reverse("lista-elecciones"), {"eleccion": finalizada.pk})

        self.assertEqual(list(respuesta.context["elecciones"]), [self.eleccion])
        self.assertEqual(respuesta.context["eleccion_actual"], self.eleccion)
        self.assertNotContains(respuesta, "Eleccion Finalizada Habilitada")
        self.assertNotContains(respuesta, reverse("escanear", args=(finalizada.pk,)))
        self.assertContains(respuesta, reverse("escanear", args=(self.eleccion.pk,)))

        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.FINALIZADA)
        respuesta = self.client.get(reverse("lista-elecciones"))
        self.assertFalse(respuesta.context["elecciones"].exists())
        self.assertContains(respuesta, "Debe haber una elección en curso para poder registrar participación.")

    def test_admin_confirma_notificaciones_solo_con_todas_las_mesas_procesadas_y_no_duplica(self):
        TipoJustificativo.objects.create(nombre="Motivo de demo")
        self.eleccion.estado = Eleccion.Estado.EN_CURSO
        self.eleccion.save(update_fields=("estado",))
        administrador = get_user_model().objects.create_user(username="admin-notificaciones-ausentes")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(administrador)
        url = reverse("confirmar-notificaciones-ausentes", args=(self.eleccion.pk,))
        destino = f"{reverse('lista-elecciones')}?eleccion={self.eleccion.pk}"
        fecha_limite = timezone.localdate() + timedelta(days=5)
        datos_confirmacion = {
            "fecha_limite_justificacion_electores": fecha_limite.isoformat(),
        }

        Mesa.objects.filter(pk=self.mesa_a.pk).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        incompleto = self.client.post(url, datos_confirmacion)
        self.assertRedirects(incompleto, destino, fetch_redirect_response=False)
        self.assertEqual(self.eleccion.envios_notificacion.count(), 0)

        Mesa.objects.filter(pk=self.mesa_b.pk).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        RegistroParticipacion.objects.create(
            registro_padron=self.registros_a[0],
            mesa=self.mesa_a,
            registrada_por=self.administrativo,
            metodo=RegistroParticipacion.Metodo.QR,
        )
        dashboard = self.client.get(reverse("lista-elecciones"), {"eleccion": self.eleccion.pk})
        self.assertContains(dashboard, "Confirmar escaneo y notificar ausentes")
        self.assertContains(dashboard, 'name="fecha_limite_justificacion_electores"')
        self.assertContains(dashboard, 'id="dialogo-confirmar-notificaciones-ausentes"')
        self.assertContains(dashboard, "dialogo.showModal()")

        respuesta = self.client.post(url, datos_confirmacion)
        self.assertRedirects(respuesta, destino, fetch_redirect_response=False)
        self.assertEqual(self.eleccion.envios_notificacion.count(), 1)
        self.eleccion.refresh_from_db()
        self.assertIsNotNone(self.eleccion.notificaciones_ausentes_confirmadas_en)
        self.assertEqual(
            self.eleccion.justificacion_electores_habilitada_en,
            self.eleccion.notificaciones_ausentes_confirmadas_en,
        )
        self.assertEqual(self.eleccion.fecha_limite_justificacion_electores, fecha_limite)
        self.assertEqual(self.eleccion.envios_notificacion.get().elector, self.registros_a[0].elector)

        self.client.post(url, datos_confirmacion)
        self.assertEqual(self.eleccion.envios_notificacion.count(), 1)

    def test_confirmacion_requiere_fecha_limite_futura_o_de_hoy(self):
        self.eleccion.estado = Eleccion.Estado.EN_CURSO
        self.eleccion.save(update_fields=("estado",))
        administrador = get_user_model().objects.create_user(username="admin-fecha-ausentes")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        Mesa.objects.filter(eleccion=self.eleccion).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        self.client.force_login(administrador)
        url = reverse("confirmar-notificaciones-ausentes", args=(self.eleccion.pk,))
        destino = f"{reverse('lista-elecciones')}?eleccion={self.eleccion.pk}"

        for datos in (
            {},
            {"fecha_limite_justificacion_electores": (timezone.localdate() - timedelta(days=1)).isoformat()},
        ):
            with self.subTest(datos=datos):
                respuesta = self.client.post(url, datos)
                self.assertRedirects(respuesta, destino, fetch_redirect_response=False)
                self.eleccion.refresh_from_db()
                self.assertIsNone(self.eleccion.notificaciones_ausentes_confirmadas_en)
                self.assertIsNone(self.eleccion.justificacion_electores_habilitada_en)
                self.assertEqual(self.eleccion.envios_notificacion.count(), 0)

    def test_confirmacion_previa_puede_habilitar_periodo_sin_reenviar_notificaciones(self):
        self.eleccion.estado = Eleccion.Estado.EN_CURSO
        self.eleccion.notificaciones_ausentes_confirmadas_en = timezone.now()
        self.eleccion.save(update_fields=("estado", "notificaciones_ausentes_confirmadas_en"))
        administrador = get_user_model().objects.create_user(username="admin-reabre-plazo-ausentes")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        self.client.force_login(administrador)
        url = reverse("confirmar-notificaciones-ausentes", args=(self.eleccion.pk,))
        fecha_limite = timezone.localdate() + timedelta(days=3)

        respuesta = self.client.post(
            url,
            {"fecha_limite_justificacion_electores": fecha_limite.isoformat()},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.eleccion.refresh_from_db()
        self.assertIsNotNone(self.eleccion.justificacion_electores_habilitada_en)
        self.assertEqual(self.eleccion.fecha_limite_justificacion_electores, fecha_limite)
        self.assertEqual(self.eleccion.envios_notificacion.count(), 0)

    def test_confirmacion_genera_justificativo_demo_para_el_elector_ausente(self):
        TipoJustificativo.objects.create(nombre="Motivo de demo")
        self.eleccion.estado = Eleccion.Estado.EN_CURSO
        self.eleccion.save(update_fields=("estado",))
        administrador = get_user_model().objects.create_user(username="admin-abre-justificativos")
        AsignacionRol.objects.create(
            usuario=administrador,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )
        Mesa.objects.filter(eleccion=self.eleccion).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        RegistroParticipacion.objects.create(
            registro_padron=self.registros_a[0],
            mesa=self.mesa_a,
            registrada_por=self.administrativo,
            metodo=RegistroParticipacion.Metodo.MANUAL,
        )
        fecha_limite = timezone.localdate() + timedelta(days=5)
        self.client.force_login(administrador)

        respuesta = self.client.post(
            reverse("confirmar-notificaciones-ausentes", args=(self.eleccion.pk,)),
            {"fecha_limite_justificacion_electores": fecha_limite.isoformat()},
        )

        self.assertEqual(respuesta.status_code, 302)
        elector = self.registros_a[0].elector
        usuario_elector = get_user_model().objects.create_user(username="elector-justifica-ausencia")
        PerfilUsuario.objects.create(usuario=usuario_elector, elector=elector)
        self.client.force_login(usuario_elector)
        respuesta = self.client.get(reverse("mis-justificativos"))

        self.assertTrue(respuesta.context["puede_presentar_justificativo_electoral"])
        self.assertTrue(
            JustificativoAusencia.objects.filter(
                registro_padron=self.registros_a[0],
                ausencia=JustificativoAusencia.Ausencia.VOTAR,
            ).exists()
        )

    def test_administrativo_no_puede_confirmar_notificaciones_a_ausentes(self):
        self.eleccion.estado = Eleccion.Estado.EN_CURSO
        self.eleccion.save(update_fields=("estado",))
        Mesa.objects.filter(eleccion=self.eleccion).update(estado_escaneo=Mesa.EstadoEscaneo.PROCESADA)
        self.client.force_login(self.administrativo)

        respuesta = self.client.post(
            reverse("confirmar-notificaciones-ausentes", args=(self.eleccion.pk,))
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.eleccion.envios_notificacion.count(), 0)
