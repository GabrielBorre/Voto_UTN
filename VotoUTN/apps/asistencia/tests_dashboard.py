from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.asistencia.dashboard import FiltrosDashboard, construir_dashboard
from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionSede
from apps.elecciones.views import MESAS_POR_PAGINA
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede
from apps.usuarios.models import AsignacionRol


class DashboardParticipacionTests(TestCase):
    def setUp(self):
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion Dashboard", fecha_inicio=date(2026, 8, 3), fecha_fin=date(2026, 8, 3)
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
        elector = Elector.objects.create(legajo=f"L{indice}", nombre=f"Elector {indice}", dni=f"3000000{indice}")
        registro = RegistroPadron.objects.create(
            elector=elector, eleccion=self.eleccion, eleccion_claustro_departamento=self.configuracion, sede=sede
        )
        AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa)
        return registro

    def registrar_participacion(self, registro, mesa):
        return RegistroParticipacion.objects.create(
            registro_padron=registro, mesa=mesa, registrada_por=self.administrativo, metodo="qr"
        )

    def pendientes(self, datos):
        return [mesa.numero for mesa in datos["mesas"] if not mesa.escaneada]

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

        escaneadas = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard(escaneo="escaneadas"))
        sin_escanear = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard(escaneo="pendientes"))

        self.assertEqual([mesa.numero for mesa in escaneadas["mesas"]], [1])
        self.assertEqual([mesa.numero for mesa in sin_escanear["mesas"]], [2])
        self.assertEqual((escaneadas["mesas_total"], sin_escanear["mesas_escaneadas"]), (2, 1))
        self.assertEqual(FiltrosDashboard.desde_parametros({"escaneo": "cualquiera"}).escaneo, "")

    def test_metricas_de_justificativos_sobre_ausentes_de_mesas_escaneadas(self):
        tipo = TipoJustificativo.objects.create(nombre="Salud")
        self.registrar_participacion(self.registros_a[0], self.mesa_a)
        self.crear_registro(5, self.mesa_a, self.sede_a)
        # El elector de una mesa sin escanear todavía puede votar: no cuenta como ausente.
        JustificativoAusencia.objects.create(registro_padron=self.registros_b[0], tipo=tipo, detalle="x")
        justificativo = JustificativoAusencia.objects.create(registro_padron=self.registros_a[1], tipo=tipo, detalle="x")

        pendiente = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())
        self.assertEqual((pendiente["electores_ausentes"], pendiente["justificativos_recibidos"]), (2, 1))
        self.assertEqual((pendiente["justificativos_recibidos_pct"], pendiente["justificativos_confirmados_pct"]), (50, 0))

        justificativo.estado = JustificativoAusencia.Estado.APROBADO
        justificativo.save()
        aprobado = construir_dashboard(self.administrativo, self.eleccion, FiltrosDashboard())
        self.assertEqual((aprobado["justificativos_confirmados"], aprobado["justificativos_confirmados_pct"]), (1, 100))

    def test_historial_compara_participacion_entre_elecciones(self):
        self.registrar_participacion(self.registros_a[0], self.mesa_a)
        anterior = Eleccion.objects.create(
            nombre="Eleccion Anterior", fecha_inicio=date(2025, 8, 3), fecha_fin=date(2025, 8, 3),
            estado=Eleccion.Estado.CERRADA,
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
        RegistroParticipacion.objects.create(
            registro_padron=registro, mesa=mesa, registrada_por=self.administrativo, metodo="qr"
        )
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
            nombre="Ajena", fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 1), estado=Eleccion.Estado.CERRADA
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
