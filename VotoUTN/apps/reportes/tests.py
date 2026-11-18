import csv
import re
from io import BytesIO, StringIO
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import make_aware
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionClaustroTurno,
)
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import EmisionPadronImprimible, Elector, RegistroPadron, SolicitudCambioSede
from apps.padron.services import rehabilitar_cambios_padron
from apps.parametros.models import Claustro, Departamento, Sede, Turno
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    PuestoEleccion,
)
from apps.reportes.services import valor_csv
from apps.reportes.services_boletas_pdf import (
    PAGINA,
    _clasificar_puesto,
    _crear_filas_boletas,
    _dibujar_boleta_cuadrante,
    _obtener_boletas,
    generar_boletas_pdf,
    validar_boletas_pdf,
)
from apps.reportes.services_pdf import (
    ALTO_PAGINA,
    ANCHO_COLUMNA_QR,
    ANCHO_TABLA,
    COL_TROQUEL,
    ELECTORES_POR_PAGINA,
    LADO_QR_ELECTOR,
    MARGEN,
    _agrupar_padrones_por_mesa,
    _construir_tabla,
    _construir_troquel,
    _dibujar_caratula,
    _generar_qr_vectorial,
    generar_padron_pdf,
    validar_padron_para_pdf,
)
from apps.usuarios.models import AsignacionRol


def contar_paginas_pdf(contenido: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", contenido))


class ReportesCSVTests(TestCase):
    def test_valor_csv_sanitiza_formulas(self):
        self.assertEqual(valor_csv("=1+1"), "'=1+1")
        self.assertEqual(valor_csv("+SUM(A1:A2)"), "'+SUM(A1:A2)")
        self.assertEqual(valor_csv("-10"), "'-10")
        self.assertEqual(valor_csv("@cmd"), "'@cmd")
        self.assertEqual(valor_csv("Ana Perez"), "Ana Perez")
        self.assertEqual(valor_csv(None), "")


class ReportesViewsTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            habilitada=False,
        )
        self.usuario = get_user_model().objects.create_user(username="admin", password="clave")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )

    def test_gestionar_reportes_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("gestionar-reportes", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertTemplateUsed(respuesta, "reportes/gestion.html")
        self.assertContains(respuesta, 'class="toolbar reports-grid"')
        self.assertContains(respuesta, 'class="option report-option"', count=4)
        self.assertContains(respuesta, 'class="report-actions"', count=4)
        self.assertContains(respuesta, "Padrón imprimible no disponible")
        self.assertContains(respuesta, "Boletas no disponibles")
        self.assertContains(respuesta, "Generar padrón imprimible")
        self.assertContains(respuesta, "disabled")
        self.assertContains(
            respuesta,
            '<a class="active" href="/gestion/elecciones/">Configurar elección</a>',
        )
        self.assertContains(respuesta, reverse("configurar-eleccion", args=(self.eleccion.id,)))
        self.assertContains(respuesta, "Volver a configuración", count=1)

    def test_exportar_reporte_usa_ruta_publica_existente(self):
        self.client.login(username="admin", password="clave")

        respuesta = self.client.get(reverse("exportar-reporte", args=(self.eleccion.id, "padron")))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])

    def test_reportes_exporta_padron_y_asignacion_de_sedes(self):
        self.client.force_login(self.usuario)

        pantalla = self.client.get(reverse("gestionar-reportes", args=(self.eleccion.id,)))
        respuesta = self.client.get(reverse("exportar-reporte", args=(self.eleccion.id, "asignacion-sedes")))

        self.assertContains(pantalla, "Exportar padrón")
        self.assertContains(pantalla, "Exportar asignación de sedes")
        self.assertContains(pantalla, reverse("exportar-reporte", args=(self.eleccion.id, "asignacion-sedes")))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('filename="asignacion-sedes_', respuesta["Content-Disposition"])
        self.assertIn("sede_asignada", respuesta.content.decode("utf-8-sig"))

    def test_generar_boletas_pdf_sin_candidatos_redirige_con_mensaje(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("generar-boletas-pdf", args=(self.eleccion.id,)),
            follow=True,
        )

        self.assertRedirects(
            respuesta,
            reverse("gestionar-reportes", args=(self.eleccion.id,)),
        )
        mensajes = [str(mensaje) for mensaje in respuesta.context["messages"]]
        self.assertTrue(any("no tiene listas activas con candidatos" in mensaje for mensaje in mensajes))


class ExportarInfractoresTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion Infractores",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
            estado=Eleccion.Estado.FINALIZADA,
        )
        self.sede = Sede.objects.create(nombre="Medrano")
        claustro = Claustro.objects.create(nombre="Estudiantes")
        departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=claustro)
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=eleccion_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
            estado_escaneo=Mesa.EstadoEscaneo.PROCESADA,
        )
        self.usuario = get_user_model().objects.create_user(username="admin-infractores", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)
        self.tipo = TipoJustificativo.objects.create(nombre="Enfermedad")

    def crear_registro(self, dni, *, ausente):
        elector = Elector.objects.create(legajo=f"L{dni}", nombre=f"Elector {dni}", dni=dni)
        registro = RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        AsignacionMesa.objects.create(registro_padron=registro, mesa=self.mesa)
        if ausente:
            RegistroParticipacion.objects.create(
                registro_padron=registro,
                mesa=self.mesa,
                registrada_por=self.usuario,
                metodo=RegistroParticipacion.Metodo.QR,
            )
        return registro

    def crear_justificativo(self, registro, estado, ausencia=JustificativoAusencia.Ausencia.VOTAR):
        return JustificativoAusencia.objects.create(
            registro_padron=registro,
            ausencia=ausencia,
            tipo=self.tipo,
            detalle="Detalle",
            estado=estado,
        )

    def exportar(self):
        self.client.force_login(self.usuario)
        return self.client.get(reverse("exportar-reporte", args=(self.eleccion.id, "infractores")))

    def test_dashboard_historial_muestra_exportacion_de_infractores(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("dashboard-historial-eleccion", args=(self.eleccion.pk,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Justificativos")
        self.assertContains(
            respuesta,
            reverse("exportar-reporte", args=(self.eleccion.pk, "infractores")),
        )
        self.assertContains(respuesta, "Exportar infractores")

    def test_dashboard_historial_desactiva_exportacion_con_justificativos_pendientes(self):
        registro = self.crear_registro("30000002", ausente=True)
        self.crear_justificativo(registro, JustificativoAusencia.Estado.PENDIENTE)
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("dashboard-historial-eleccion", args=(self.eleccion.pk,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Exportar infractores")
        self.assertNotContains(
            respuesta,
            reverse("exportar-reporte", args=(self.eleccion.pk, "infractores")),
        )

    def test_lista_solo_ausentes_sin_justificativo_aprobado(self):
        self.crear_registro("30000001", ausente=False)
        self.crear_registro("30000002", ausente=True)
        justificado = self.crear_registro("30000003", ausente=True)
        self.crear_justificativo(justificado, JustificativoAusencia.Estado.APROBADO)
        rechazado = self.crear_registro("30000004", ausente=True)
        self.crear_justificativo(rechazado, JustificativoAusencia.Estado.RECHAZADO)
        justificado_como_autoridad = self.crear_registro("30000005", ausente=True)
        self.crear_justificativo(
            justificado_como_autoridad,
            JustificativoAusencia.Estado.APROBADO,
            ausencia=JustificativoAusencia.Ausencia.AUTORIDAD,
        )

        respuesta = self.exportar()

        self.assertEqual(respuesta.status_code, 200)
        filas = list(csv.reader(StringIO(respuesta.content.decode("utf-8-sig"))))
        estados_por_dni = {fila[2]: fila[5] for fila in filas[1:]}
        self.assertEqual(
            estados_por_dni,
            {
                "30000002": "sin_justificativo",
                "30000004": "rechazado",
                "30000005": "sin_justificativo",
            },
        )

    def test_no_exporta_infractores_si_la_eleccion_no_esta_finalizada(self):
        Eleccion.objects.filter(pk=self.eleccion.pk).update(estado=Eleccion.Estado.EN_CURSO)
        self.crear_registro("30000002", ausente=True)

        respuesta = self.exportar()

        self.assertEqual(respuesta.status_code, 403)


class PadronPDFTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion Oficio", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8),
            estado=Eleccion.Estado.EN_CURSO,
            fecha_cierre_solicitudes_cambio_sede=timezone.localdate() - timedelta(days=1),
        )
        self.sede = Sede.objects.create(nombre="Campus Central")
        self.turno = Turno.objects.create(nombre="Manana", hora_inicio=time(8), hora_fin=time(12))
        self.claustro = Claustro.objects.create(nombre="Estudiantes")
        self.departamento = Departamento.objects.create(nombre="Sistemas", codigo="K")
        EleccionSede.objects.create(eleccion=self.eleccion, sede=self.sede)
        self.eleccion_claustro = EleccionClaustro.objects.create(eleccion=self.eleccion, claustro=self.claustro)
        EleccionClaustroTurno.objects.create(eleccion_claustro=self.eleccion_claustro, turno=self.turno)
        self.configuracion = EleccionClaustroDepartamento.objects.create(eleccion_claustro=self.eleccion_claustro, departamento=self.departamento)
        EleccionClaustroDepartamentoSede.objects.create(eleccion_claustro_departamento=self.configuracion, sede=self.sede)
        self.mesa = Mesa.objects.create(
            eleccion=self.eleccion,
            numero=1,
            eleccion_claustro_departamento=self.configuracion,
            sede=self.sede,
        )
        self.usuario = get_user_model().objects.create_user(username="admin-reportes", password="clave")
        AsignacionRol.objects.create(usuario=self.usuario, rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA, eleccion=self.eleccion)

    def crear_electores(self, cantidad, mesa="usar_default", sede="usar_default", numero_inicial=1):
        mesa_asignada = self.mesa if mesa == "usar_default" else mesa
        sede_asignada = self.sede if sede == "usar_default" else sede
        registros = []
        for indice in range(numero_inicial, numero_inicial + cantidad):
            elector = Elector.objects.create(
                legajo=f"E{indice:05d}",
                nombre=f"Elector {indice:03d}",
                dni=f"3{indice:07d}",
            )
            registro = RegistroPadron.objects.create(
                elector=elector,
                eleccion=self.eleccion,
                eleccion_claustro_departamento=self.configuracion,
                sede=None if not AsignacionAutoridad.objects.filter(mesa=mesa_asignada).exists() else sede_asignada,
            )
            if mesa_asignada is not None:
                AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa_asignada)
                if not AsignacionAutoridad.objects.filter(mesa=mesa_asignada, turno=self.turno).exists():
                    candidatura = CandidaturaAutoridad.objects.create(registro_padron=registro, cargada_por=self.usuario)
                    AsignacionAutoridad.objects.create(
                        registro_padron=registro,
                        candidatura=candidatura,
                        mesa=mesa_asignada,
                        turno=self.turno,
                        asignada_por=self.usuario,
                    )
            registros.append(registro)
        return registros

    def test_genera_pdf_con_menos_de_15_electores(self):
        self.crear_electores(5)

        contenido = generar_padron_pdf(self.eleccion)

        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertEqual(contar_paginas_pdf(contenido), 2)  # caratula + 1 hoja

    def test_columna_apellido_y_nombre_usa_apellido_primero(self):
        registro = self.crear_electores(1)[0]
        registro.elector.apellido = "Gomez"
        registro.elector.nombre = "Maria Elena"

        with (
            patch("apps.reportes.services_pdf._construir_espacio_firma", return_value="firma"),
            patch("apps.reportes.services_pdf._construir_troquel", return_value="troquel"),
        ):
            tabla = _construir_tabla(self.eleccion, self.mesa, [registro], 1, 20)

        self.assertEqual(tabla._cellvalues[1][2].text, "Gomez, Maria Elena")

    def test_troquel_usa_apellido_y_nombre(self):
        registro = self.crear_electores(1)[0]
        registro.elector.apellido = "Gomez"
        registro.elector.nombre = "Maria Elena"

        troquel = _construir_troquel(self.eleccion, self.mesa, registro, 20)

        texto_troquel = troquel._cellvalues[0][1]
        self.assertEqual(texto_troquel._cellvalues[0][0].text, "Gomez, Maria Elena")

    @override_settings(CLAVE_FIRMA_QR="clave-de-prueba-qr")
    def test_qr_vectorial_conserva_payload_y_margen_de_cuatro_modulos(self):
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M

        registro = self.crear_electores(1)[0]
        with patch("apps.reportes.services_pdf._generar_qr_vectorial", wraps=_generar_qr_vectorial) as generar:
            troquel = _construir_troquel(self.eleccion, self.mesa, registro, 21 * mm)

        payload, lado = generar.call_args.args
        self.assertEqual(
            ServicioRegistroParticipacion.parsear_codigo_qr(payload),
            (self.eleccion.id, self.mesa.numero, registro.identificador_qr),
        )
        referencia = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=4)
        referencia.add_data(payload)
        referencia.make(fit=True)
        matriz = referencia.get_matrix()
        modulo = lado / len(matriz)
        dibujo = troquel._cellvalues[0][0]
        fondo, trazado = dibujo.contents
        self.assertEqual(fondo.fillColor, colors.white)
        self.assertEqual(trazado.fillColor, colors.black)
        coordenadas = []
        for fila, modulos in enumerate(matriz):
            for columna, oscuro in enumerate(modulos):
                if oscuro:
                    x = columna * modulo
                    y = lado - (fila + 1) * modulo
                    coordenadas.extend([x, y, x + modulo, y, x + modulo, y + modulo, x, y + modulo])
        self.assertEqual(trazado.points, coordenadas)
        self.assertGreaterEqual(min(trazado.points), 4 * modulo - 1e-8)
        self.assertLessEqual(max(trazado.points), lado - 4 * modulo + 1e-8)
        buffer = BytesIO()
        lienzo = Canvas(buffer, pageCompression=0)
        dibujo.drawOn(lienzo, 0, 0)
        lienzo.save()
        self.assertNotIn(b"/Subtype /Image", buffer.getvalue())

    def test_genera_pdf_con_exactamente_15_electores(self):
        self.crear_electores(ELECTORES_POR_PAGINA)

        contenido = generar_padron_pdf(self.eleccion)

        self.assertEqual(contar_paginas_pdf(contenido), 2)

    def test_genera_pdf_con_mas_de_15_electores_crea_multiples_paginas(self):
        self.crear_electores(ELECTORES_POR_PAGINA + 1)

        contenido = generar_padron_pdf(self.eleccion)

        self.assertEqual(contar_paginas_pdf(contenido), 3)

    def test_marca_de_agua_en_caratulas_y_todas_las_hojas_sin_tapar_qr(self):
        otra_mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, eleccion_claustro_departamento=self.configuracion, sede=self.sede
        )
        self.crear_electores(ELECTORES_POR_PAGINA + 1)
        self.crear_electores(1, mesa=otra_mesa, numero_inicial=100)

        with patch(
            "apps.reportes.services_pdf.pdfcanvas.Canvas",
            side_effect=lambda *args, **kwargs: Canvas(*args, pageCompression=0, **kwargs),
        ):
            contenido = generar_padron_pdf(self.eleccion)

        paginas = [
            stream for stream in re.findall(rb"stream\r?\n(.*?)endstream", contenido, re.DOTALL)
            if b"(Demo Proyecto Final) Tj" in stream
        ]
        self.assertEqual(contar_paginas_pdf(contenido), 5)
        self.assertEqual(len(paginas), 5)
        for indice, pagina in enumerate(paginas):
            with self.subTest(pagina=indice):
                for texto in (b"(Demo Proyecto Final) Tj", b"(VOTO UTN) Tj"):
                    self.assertEqual(pagina.count(texto), 1)
                    self.assertLess(pagina.index(texto), pagina.index(b"1 1 1 rg"))
                self.assertIn(b" 0 Tm (Demo Proyecto Final) Tj", pagina)
                self.assertIn(b" -56 Tm (VOTO UTN) Tj", pagina)

    def test_cada_mesa_tiene_una_caratula_con_codigo_y_qr_de_mesa(self):
        otra_mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, eleccion_claustro_departamento=self.configuracion, sede=self.sede
        )
        self.crear_electores(2)
        self.crear_electores(2, mesa=otra_mesa, numero_inicial=10)

        with patch("apps.reportes.services_pdf._dibujar_caratula") as caratula:
            contenido = generar_padron_pdf(self.eleccion)

        self.assertEqual([llamada.args[2].codigo for llamada in caratula.call_args_list], ["K-001", "K-002"])
        self.assertEqual(contar_paginas_pdf(contenido), 4)  # caratula + hoja por mesa

    def test_el_pie_numera_las_hojas_de_cada_mesa_sin_contar_las_caratulas(self):
        otra_mesa = Mesa.objects.create(
            eleccion=self.eleccion, numero=2, eleccion_claustro_departamento=self.configuracion, sede=self.sede
        )
        self.crear_electores(ELECTORES_POR_PAGINA + 1)
        self.crear_electores(1, mesa=otra_mesa, numero_inicial=100)

        with patch("apps.reportes.services_pdf._dibujar_pie_pagina") as pie:
            generar_padron_pdf(self.eleccion)

        self.assertEqual([llamada.args[1:] for llamada in pie.call_args_list], [(1, 2), (2, 2), (1, 1)])

    @override_settings(CLAVE_FIRMA_QR="clave-de-prueba-qr")
    def test_la_caratula_incluye_un_qr_de_mesa_firmado(self):
        self.crear_electores(1)

        with patch("apps.reportes.services_pdf._generar_qr_vectorial", wraps=_generar_qr_vectorial) as generar:
            _dibujar_caratula(Canvas(BytesIO()), self.eleccion, self.mesa)

        payload = generar.call_args.args[0]
        self.assertEqual(ServicioRegistroParticipacion.parsear_codigo_qr_mesa(payload), (self.eleccion.id, 1))

    def test_caratula_identifica_la_mesa_especial_sin_cambiar_su_qr(self):
        self.mesa.es_especial = True
        self.mesa.save(update_fields=("es_especial",))
        lienzo = Canvas(BytesIO())
        with patch.object(lienzo, "drawCentredString", wraps=lienzo.drawCentredString) as dibujar:
            with patch("apps.reportes.services_pdf._generar_qr_vectorial", wraps=_generar_qr_vectorial) as generar:
                _dibujar_caratula(lienzo, self.eleccion, self.mesa)
        self.assertIn("INFORMACIÓN DE MESA ESPECIAL", [llamada.args[2] for llamada in dibujar.call_args_list])
        self.assertEqual(
            ServicioRegistroParticipacion.parsear_codigo_qr_mesa(generar.call_args.args[0]),
            (self.eleccion.id, self.mesa.numero),
        )

    def test_ultima_pagina_contiene_el_resto_de_electores(self):
        self.crear_electores(ELECTORES_POR_PAGINA + 2)

        grupos = _agrupar_padrones_por_mesa(self.eleccion)
        electores_mesa = grupos[0]["padrones"]
        lotes = [
            electores_mesa[inicio: inicio + ELECTORES_POR_PAGINA]
            for inicio in range(0, len(electores_mesa), ELECTORES_POR_PAGINA)
        ]

        self.assertEqual([len(lote) for lote in lotes], [ELECTORES_POR_PAGINA, 2])

    def test_bloquea_generacion_sin_mesa_asignada(self):
        self.crear_electores(3)
        self.crear_electores(1, mesa=None, numero_inicial=100)

        validacion = validar_padron_para_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertTrue(any("mesa" in motivo for motivo in validacion.motivos))
        with self.assertRaises(ValueError):
            generar_padron_pdf(self.eleccion)

    def test_permite_generacion_sin_sede_donde_cursa(self):
        self.crear_electores(3)
        self.crear_electores(1, sede=None, numero_inicial=200)

        validacion = validar_padron_para_pdf(self.eleccion)

        self.assertTrue(validacion.apto)
        self.assertTrue(generar_padron_pdf(self.eleccion).startswith(b"%PDF"))

    def test_bloquea_emision_si_falta_un_titular_por_turno(self):
        self.crear_electores(2)
        AsignacionAutoridad.objects.filter(mesa=self.mesa, turno=self.turno).delete()

        validacion = validar_padron_para_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertTrue(any("no tiene titular asignado" in motivo for motivo in validacion.motivos))

    def test_vista_genera_pdf_descargable(self):
        self.crear_electores(3)
        self.client.login(username="admin-reportes", password="clave")

        respuesta = self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])
        self.assertTrue(EmisionPadronImprimible.objects.filter(eleccion_claustro=self.eleccion_claustro, estado="vigente").exists())
        self.assertTrue(RegistroPadron.objects.filter(eleccion=self.eleccion, qr_generado_en__isnull=False).exists())

    def test_vista_rechaza_solicitudes_de_cambio_de_sede_pendientes(self):
        registro = self.crear_electores(1)[0]
        self.client.force_login(self.usuario)
        destino = Sede.objects.create(nombre="Sede Destino")
        SolicitudCambioSede.objects.create(
            registro_padron=registro, sede_origen=self.sede, sede_destino=destino,
        )

        respuesta = self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.pk,)), follow=True)

        self.assertRedirects(respuesta, reverse("gestionar-reportes", args=(self.eleccion.pk,)))
        self.assertTrue(any("solicitudes de cambio de sede pendientes" in str(m) for m in respuesta.context["messages"]))
        self.assertFalse(EmisionPadronImprimible.objects.exists())
        self.assertFalse(RegistroPadron.objects.filter(eleccion=self.eleccion, qr_generado_en__isnull=False).exists())

    def test_vista_emite_con_plazo_de_cambio_de_sede_abierto(self):
        self.crear_electores(1)
        self.client.force_login(self.usuario)
        self.eleccion.fecha_cierre_solicitudes_cambio_sede = timezone.localdate()
        self.eleccion.save(update_fields=("fecha_cierre_solicitudes_cambio_sede",))

        respuesta = self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.pk,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertTrue(EmisionPadronImprimible.objects.filter(eleccion_claustro=self.eleccion_claustro, estado="vigente").exists())

    def test_vista_bloquea_y_redirige_cuando_falta_informacion(self):
        self.crear_electores(1, mesa=None)
        self.client.login(username="admin-reportes", password="clave")

        respuesta = self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.id,)), follow=True)

        self.assertRedirects(respuesta, reverse("gestionar-reportes", args=(self.eleccion.id,)))
        mensajes = [str(mensaje) for mensaje in respuesta.context["messages"]]
        self.assertTrue(any("mesa" in mensaje for mensaje in mensajes))

    def test_no_se_puede_rehabilitar_una_emision_en_curso(self):
        registros = self.crear_electores(1)
        identificador_anterior = registros[0].identificador_qr
        self.client.login(username="admin-reportes", password="clave")
        self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.id,)))

        with self.assertRaisesMessage(ValueError, "No se pueden rehabilitar"):
            rehabilitar_cambios_padron(self.eleccion_claustro, self.usuario)

        registros[0].refresh_from_db()
        self.assertEqual(EmisionPadronImprimible.objects.get().estado, "vigente")
        self.assertIsNotNone(registros[0].qr_generado_en)
        self.assertEqual(registros[0].numero_mesa_qr, self.mesa.numero)
        self.assertEqual(registros[0].identificador_qr, identificador_anterior)

    def test_pdf_solo_se_puede_generar_en_curso(self):
        self.crear_electores(1)
        self.client.force_login(self.usuario)
        for estado in (Eleccion.Estado.EN_PREPARACION, Eleccion.Estado.PUBLICADA, Eleccion.Estado.FINALIZADA):
            with self.subTest(estado=estado):
                self.eleccion.estado = estado
                self.eleccion.save(update_fields=("estado",))
                self.assertFalse(validar_padron_para_pdf(self.eleccion).apto)
                with self.assertRaisesMessage(ValueError, "en curso"):
                    generar_padron_pdf(self.eleccion)
                respuesta = self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.pk,)))
                self.assertEqual(respuesta.status_code, 302)
                self.assertFalse(EmisionPadronImprimible.objects.exists())

    def test_reimpresion_preserva_los_qr_y_la_emision_vigente(self):
        registro = self.crear_electores(1)[0]
        self.client.force_login(self.usuario)
        url = reverse("generar-padron-pdf", args=(self.eleccion.pk,))
        self.assertEqual(self.client.post(url).status_code, 200)
        registro.refresh_from_db()
        marcas = (registro.identificador_qr, registro.qr_generado_en, registro.numero_mesa_qr)
        self.assertEqual(self.client.post(url).status_code, 200)
        registro.refresh_from_db()
        self.assertEqual((registro.identificador_qr, registro.qr_generado_en, registro.numero_mesa_qr), marcas)
        self.assertEqual(EmisionPadronImprimible.objects.count(), 1)


class BoletasPDFTests(TestCase):
    def test_nombres_renombrados_conservan_las_categorias_de_boleta(self):
        boleta = {"claustros": {"Estudiantes"}, "departamento": None}
        self.assertEqual(
            _clasificar_puesto(boleta, {"organo": "Consejo Superior", "nombre": "Consejero/a Superior"}),
            "superior",
        )
        self.assertEqual(
            _clasificar_puesto(boleta, {"organo": "Consejo Departamental", "nombre": "Consejero/a Ciencias Básicas"}),
            "ciencias_basicas",
        )

    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Elección de boletas",
            fecha_inicio=inicio,
            fecha_fin=inicio + timedelta(hours=8),
        )
        self.claustro = Claustro.objects.create(nombre="Estudiantes boletas")
        self.eleccion_claustro = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=self.claustro,
        )
        self.departamento = Departamento.objects.create(
            nombre="Sistemas boletas",
            codigo="SB",
        )
        self.configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=self.eleccion_claustro,
            departamento=self.departamento,
        )
        self.organo = OrganoElectivo.objects.create(nombre="Consejo Departamental")
        self.cargo = CargoElectivo.objects.create(
            organo=self.organo,
            nombre="Consejero/a",
            permite_filtrar_departamentos=True,
        )
        self.puesto = PuestoEleccion.objects.create(
            puesto=self.cargo,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            cantidad_titulares=2,
            cantidad_suplentes=1,
        )
        self.usuario = get_user_model().objects.create_user(username="admin-boletas")
        AsignacionRol.objects.create(
            usuario=self.usuario,
            rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
            eleccion=self.eleccion,
        )

    def crear_presentacion(self, *, codigo, numero, nombre, elector, activa=True):
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion=codigo,
            eleccion_claustro=self.eleccion_claustro,
            numero_lista=numero,
            nombre_lista=nombre,
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion,
            eleccion_claustro=self.eleccion_claustro,
            eleccion_claustro_departamento=self.configuracion,
            nombre="Consejo Departamental",
            puesto_eleccion=self.puesto,
            activa=activa,
        )
        Candidato.objects.create(
            lista=lista,
            elector=elector,
            cargo=self.cargo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
            activo=True,
        )
        return participacion

    def crear_elector(self, indice, nombre, configuracion=None):
        elector = Elector.objects.create(
            legajo=f"B{indice:05d}",
            nombre=nombre,
            apellido="Candidata",
            dni=f"4{indice:07d}",
        )
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=configuracion or self.configuracion,
        )
        return elector

    def crear_boleta_prueba(self, claustro, departamento, organo, nombre):
        return {
            "clave_lista": (self.eleccion.pk, "10", "Lista Azul", claustro),
            "claustros": [claustro],
            "departamento": departamento,
            "puestos": [
                {
                    "organo": organo,
                    "nombre": nombre,
                    "candidatos": [],
                }
            ],
        }

    def agregar_lista_departamental(self, participacion, departamento, indice):
        alcance = participacion.eleccion_claustro
        configuracion, _ = EleccionClaustroDepartamento.objects.get_or_create(
            eleccion_claustro=alcance, departamento=departamento,
        )
        puesto, _ = PuestoEleccion.objects.get_or_create(
            puesto=self.cargo,
            eleccion_claustro=alcance,
            eleccion_claustro_departamento=configuracion,
            defaults={"cantidad_titulares": 2, "cantidad_suplentes": 1},
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion,
            eleccion_claustro=alcance,
            eleccion_claustro_departamento=configuracion,
            puesto_eleccion=puesto,
            nombre="Consejo Departamental",
        )
        Candidato.objects.create(
            lista=lista,
            elector=self.crear_elector(indice, f"Candidata {indice}", configuracion),
            cargo=self.cargo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )
        return lista

    def test_validacion_indica_cuando_no_hay_candidaturas_activas(self):
        validacion = validar_boletas_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertEqual(validacion.cantidad_boletas, 0)
        self.assertTrue(validacion.motivos)

    def test_pagina_de_boletas_usa_formato_apaisado(self):
        self.assertGreater(PAGINA[0], PAGINA[1])

    def test_genera_una_boleta_por_presentacion_y_alcance(self):
        self.crear_presentacion(
            codigo="A",
            numero="10",
            nombre="Lista Azul",
            elector=self.crear_elector(1, "Ana"),
        )
        self.crear_presentacion(
            codigo="B",
            numero="20",
            nombre="Lista Verde",
            elector=self.crear_elector(2, "Bruno"),
        )

        validacion = validar_boletas_pdf(self.eleccion)
        contenido = generar_boletas_pdf(self.eleccion)

        self.assertTrue(validacion.apto)
        self.assertEqual(validacion.cantidad_boletas, 4)
        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertEqual(contar_paginas_pdf(contenido), 2)

    def test_agrupa_puestos_de_la_misma_lista_solo_dentro_del_claustro(self):
        participacion_original = self.crear_presentacion(
            codigo="SISTEMAS-DOCENTES-2",
            numero="2",
            nombre="Lista Sistemas",
            elector=self.crear_elector(10, "Ana"),
        )
        PuestoEleccion.objects.filter(pk=self.puesto.pk).update(
            cantidad_titulares=3,
            cantidad_suplentes=3,
        )
        claustro_docentes = Claustro.objects.create(nombre="Docentes boletas")
        alcance_docentes = EleccionClaustro.objects.create(
            eleccion=self.eleccion,
            claustro=claustro_docentes,
        )
        departamento_estudiantes = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=alcance_docentes,
            departamento=self.departamento,
        )
        puesto_estudiantes = PuestoEleccion.objects.create(
            puesto=self.cargo,
            eleccion_claustro=alcance_docentes,
            eleccion_claustro_departamento=departamento_estudiantes,
            cantidad_titulares=5,
            cantidad_suplentes=5,
        )
        segunda = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion="SISTEMAS-ESTUDIANTES-2",
            eleccion_claustro=alcance_docentes,
            numero_lista="2",
            nombre_lista="Lista Sistemas",
        )
        organo_directivo = OrganoElectivo.objects.create(nombre="Consejo Directivo transversal")
        cargo_directivo = CargoElectivo.objects.create(
            organo=organo_directivo,
            nombre="Consejero/a directivo/a",
        )
        puesto_directivo_original = PuestoEleccion.objects.create(
            puesto=cargo_directivo,
            eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=5,
            cantidad_suplentes=5,
        )
        puesto_directivo_estudiantes = PuestoEleccion.objects.create(
            puesto=cargo_directivo,
            eleccion_claustro=alcance_docentes,
            cantidad_titulares=5,
            cantidad_suplentes=5,
        )
        lista_directiva_original = ListaCandidatos.objects.create(
            participacion=participacion_original,
            eleccion_claustro=self.eleccion_claustro,
            nombre="Consejo Directivo",
            puesto_eleccion=puesto_directivo_original,
        )
        lista_directiva_estudiantes = ListaCandidatos.objects.create(
            participacion=segunda,
            eleccion_claustro=alcance_docentes,
            nombre="Consejo Directivo",
            puesto_eleccion=puesto_directivo_estudiantes,
        )
        Candidato.objects.create(
            lista=lista_directiva_original,
            elector=self.crear_elector(12, "Cecilia"),
            cargo=cargo_directivo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )
        Candidato.objects.create(
            lista=lista_directiva_estudiantes,
            elector=self.crear_elector(13, "Diego", departamento_estudiantes),
            cargo=cargo_directivo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )
        elector = self.crear_elector(11, "Bruno")
        RegistroPadron.objects.filter(elector=elector).update(
            eleccion_claustro_departamento=departamento_estudiantes,
        )
        lista_estudiantes = ListaCandidatos.objects.create(
            participacion=segunda,
            eleccion_claustro=alcance_docentes,
            eleccion_claustro_departamento=departamento_estudiantes,
            nombre="Consejo Departamental",
            puesto_eleccion=puesto_estudiantes,
        )
        Candidato.objects.create(
            lista=lista_estudiantes,
            elector=elector,
            cargo=self.cargo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )
        for indice_lista, lista in enumerate(
            (
                participacion_original.listas.get(puesto_eleccion=self.puesto),
                lista_estudiantes,
                lista_directiva_original,
                lista_directiva_estudiantes,
            )
        ):
            for tipo, cantidad in (
                (Candidato.Tipo.TITULAR, lista.puesto_eleccion.cantidad_titulares),
                (Candidato.Tipo.SUPLENTE, lista.puesto_eleccion.cantidad_suplentes),
            ):
                primer_orden = 2 if tipo == Candidato.Tipo.TITULAR else 1
                for orden in range(primer_orden, cantidad + 1):
                    Candidato.objects.create(
                        lista=lista,
                        elector=self.crear_elector(
                            20 + indice_lista * 20 + orden + primer_orden * 10,
                            f"Candidato {indice_lista}-{tipo}-{orden}",
                            (
                                departamento_estudiantes
                                if lista.eleccion_claustro_id == alcance_docentes.id
                                else self.configuracion
                            ),
                        ),
                        cargo=lista.puesto_eleccion.puesto.nombre,
                        tipo=tipo,
                        orden=orden,
                    )

        boletas = _obtener_boletas(self.eleccion)
        contenido = generar_boletas_pdf(self.eleccion)

        self.assertEqual(len(boletas), 2)
        boletas_por_claustro = {
            boleta["claustros"][0]: boleta
            for boleta in boletas
        }
        boleta_estudiantes = boletas_por_claustro["Estudiantes boletas"]
        boleta_docentes = boletas_por_claustro["Docentes boletas"]
        self.assertEqual(len(boleta_docentes["puestos"]), 2)
        self.assertEqual(len(boleta_estudiantes["puestos"]), 2)
        self.assertEqual(
            {
                candidato.elector.nombre_completo
                for puesto in boleta_estudiantes["puestos"]
                for candidato in puesto["candidatos"]
            },
            {
                candidato.elector.nombre_completo
                for lista in (participacion_original.listas.get(puesto_eleccion=self.puesto), lista_directiva_original)
                for candidato in lista.candidatos.all()
            },
        )
        self.assertEqual(
            {
                candidato.elector.nombre_completo
                for puesto in boleta_docentes["puestos"]
                for candidato in puesto["candidatos"]
            },
            {
                candidato.elector.nombre_completo
                for lista in (lista_estudiantes, lista_directiva_estudiantes)
                for candidato in lista.candidatos.all()
            },
        )
        filas, puestos_sin_categoria = _crear_filas_boletas(boletas)
        self.assertEqual(puestos_sin_categoria, [])
        self.assertEqual(len(filas), 4)
        for fila in filas:
            columnas = fila["columnas"]
            if fila.get("fila_departamental"):
                self.assertEqual(
                    [columna is not None for columna in columnas],
                    [False, False, True, False],
                )
            else:
                self.assertEqual(
                    [columna is not None for columna in columnas],
                    [False, True, True, False],
                )
        self.assertEqual(contar_paginas_pdf(contenido), 2)

    def test_ciencias_basicas_ocupa_la_columna_correspondiente_al_claustro(self):
        ciencias_basicas = Departamento.objects.create(
            nombre="Ciencias Básicas",
            codigo="Z",
        )

        for claustro, columna in (
            ("Estudiantes", 3),
            ("Graduados", 3),
            ("Docentes", 3),
        ):
            boleta = self.crear_boleta_prueba(
                claustro,
                ciencias_basicas,
                "Consejo Departamental",
                "Consejero/a",
            )
            filas, puestos_sin_categoria = _crear_filas_boletas([boleta])

            self.assertEqual(puestos_sin_categoria, [])
            self.assertIsNotNone(filas[0]["columnas"][columna])
            self.assertEqual(
                sum(columna is not None for columna in filas[0]["columnas"]),
                1,
            )

    def test_estudiantes_ubica_ciencias_basicas_en_la_fila_principal_de_cada_departamento(self):
        participacion = self.crear_presentacion(
            codigo="AZUL", numero="10", nombre="Lista Azul", elector=self.crear_elector(100, "Ana"),
        )
        otra = self.crear_presentacion(
            codigo="VERDE", numero="10", nombre="Lista Verde", elector=self.crear_elector(101, "Bea"),
        )
        civil = Departamento.objects.create(nombre="Civil", codigo="C")
        ciencias_basicas = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        self.agregar_lista_departamental(participacion, civil, 102)
        lista_basicas = self.agregar_lista_departamental(participacion, ciencias_basicas, 103)

        boletas = _obtener_boletas(self.eleccion)
        filas, errores = _crear_filas_boletas(boletas)

        self.assertEqual(errores, [])
        self.assertEqual(len(boletas), 3)
        self.assertFalse(any(boleta["departamento"] == ciencias_basicas for boleta in boletas))
        filas_azules = [fila for fila in filas if any(
            columna and columna["participacion"].pk == participacion.pk for columna in fila["columnas"]
        )]
        self.assertEqual(len(filas_azules), 4)
        for fila in filas_azules:
            departamental, basicas = fila["columnas"][2:4]
            self.assertIsNotNone(departamental)
            if fila.get("fila_departamental"):
                self.assertIsNone(basicas)
            else:
                self.assertIsNotNone(basicas)
                self.assertEqual(basicas["puestos"][0]["candidatos"][0].lista_id, lista_basicas.pk)
        filas_verdes = [fila for fila in filas if any(
            columna and columna["participacion"].pk == otra.pk for columna in fila["columnas"]
        )]
        self.assertTrue(all(fila["columnas"][3] is None for fila in filas_verdes))
        with patch(
            "apps.reportes.services_boletas_pdf._dibujar_boleta_cuadrante",
            wraps=_dibujar_boleta_cuadrante,
        ) as dibujar:
            contenido = generar_boletas_pdf(self.eleccion)
        self.assertTrue(contenido.startswith(b"%PDF"))
        dibujadas = [llamada.args[1] for llamada in dibujar.call_args_list]
        self.assertEqual(dibujadas, [
            columna for fila in filas for columna in fila["columnas"] if columna is not None
        ])
        self.assertTrue(validar_boletas_pdf(self.eleccion).apto)

    def test_estudiantes_con_solo_ciencias_basicas_y_puesto_general_no_crea_departamento_aparte(self):
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="BASICAS", eleccion_claustro=self.eleccion_claustro,
            numero_lista="11", nombre_lista="Lista Básicas",
        )
        ciencias_basicas = Departamento.objects.create(nombre="Ciencias Basicas", codigo="CB")
        self.agregar_lista_departamental(participacion, ciencias_basicas, 104)
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        cargo = CargoElectivo.objects.create(organo=organo, nombre="Consejero/a directivo/a")
        puesto = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=self.eleccion_claustro, cantidad_titulares=1, cantidad_suplentes=1,
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion, eleccion_claustro=self.eleccion_claustro, puesto_eleccion=puesto,
        )
        Candidato.objects.create(
            lista=lista, elector=self.crear_elector(105, "General"), cargo=cargo.nombre,
            tipo=Candidato.Tipo.TITULAR, orden=1,
        )

        boletas = _obtener_boletas(self.eleccion)
        filas, errores = _crear_filas_boletas(boletas)

        self.assertEqual(errores, [])
        self.assertEqual(len(boletas), 1)
        self.assertIsNone(boletas[0]["departamento"])
        self.assertEqual(len(filas), 1)
        self.assertEqual([columna is not None for columna in filas[0]["columnas"]], [False, True, False, True])
        self.assertTrue(generar_boletas_pdf(self.eleccion).startswith(b"%PDF"))

    def test_estudiantes_no_imprime_basicas_en_segunda_fila_fisica(self):
        cargo = CargoElectivo.objects.create(
            organo=self.organo, nombre="Consejero/a Ciencias Básicas",
        )
        puesto = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=self.eleccion_claustro,
            cantidad_titulares=1, cantidad_suplentes=1,
        )
        for indice in range(4):
            participacion = ParticipacionPartido.objects.create(
                eleccion=self.eleccion, eleccion_claustro=self.eleccion_claustro,
                codigo_presentacion=f"BASICAS-{indice}", numero_lista=str(indice + 1),
                nombre_lista=f"Lista {indice + 1}",
            )
            lista = ListaCandidatos.objects.create(
                participacion=participacion, eleccion_claustro=self.eleccion_claustro,
                puesto_eleccion=puesto,
            )
            Candidato.objects.create(
                lista=lista, elector=self.crear_elector(120 + indice, f"Estudiante {indice}"),
                cargo=cargo.nombre, tipo=Candidato.Tipo.TITULAR, orden=1,
            )

        filas, errores = _crear_filas_boletas(_obtener_boletas(self.eleccion))

        self.assertEqual(errores, [])
        self.assertEqual(len(filas), 4)
        self.assertIsNotNone(filas[0]["columnas"][3])
        self.assertIsNone(filas[1]["columnas"][3])
        self.assertIsNotNone(filas[2]["columnas"][3])
        self.assertIsNone(filas[3]["columnas"][3])
        self.assertEqual(validar_boletas_pdf(self.eleccion).cantidad_boletas, 2)
        with patch(
            "apps.reportes.services_boletas_pdf._dibujar_boleta_cuadrante",
            wraps=_dibujar_boleta_cuadrante,
        ) as dibujar:
            contenido = generar_boletas_pdf(self.eleccion)
        self.assertEqual(contar_paginas_pdf(contenido), 2)
        self.assertEqual(dibujar.call_count, 2)

    def test_ciencias_basicas_no_se_mezcla_con_otro_claustro_de_la_misma_lista(self):
        ciencias_basicas = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="BASICAS", eleccion_claustro=self.eleccion_claustro,
            numero_lista="10", nombre_lista="Lista Azul",
        )
        self.agregar_lista_departamental(participacion, ciencias_basicas, 106)
        docentes = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Docentes"),
        )
        lista_docente = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="DOCENTES", eleccion_claustro=docentes,
            numero_lista="10", nombre_lista="Lista Azul",
        )
        self.agregar_lista_departamental(lista_docente, self.departamento, 107)
        lista_basicas_docente = self.agregar_lista_departamental(lista_docente, ciencias_basicas, 108)

        boletas = _obtener_boletas(self.eleccion)
        filas, errores = _crear_filas_boletas(boletas)

        self.assertEqual(errores, [])
        self.assertEqual(len(boletas), 2)
        filas_docentes = [
            fila for fila in filas
            if any(columna and columna["participacion"].pk == lista_docente.pk for columna in fila["columnas"])
        ]
        self.assertEqual(len(filas_docentes), 2)
        for fila in filas_docentes:
            self.assertIsNotNone(fila["columnas"][2])
            self.assertEqual(
                fila["columnas"][3]["puestos"][0]["candidatos"][0].lista_id, lista_basicas_docente.pk,
            )
        fila_estudiantes = next(
            fila for fila in filas
            if any(columna and columna["participacion"].pk == participacion.pk for columna in fila["columnas"])
        )
        self.assertEqual(
            fila_estudiantes["columnas"][3]["puestos"][0]["candidatos"][0].lista_id,
            participacion.listas.get().pk,
        )

    def test_docentes_repite_ciencias_basicas_junto_a_cada_departamento_de_la_misma_lista(self):
        docentes = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Docentes"),
        )
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="DOC-AZUL", eleccion_claustro=docentes,
            numero_lista="10", nombre_lista="Lista Azul",
        )
        otra = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="DOC-VERDE", eleccion_claustro=docentes,
            numero_lista="10", nombre_lista="Lista Verde",
        )
        civil = Departamento.objects.create(nombre="Civil", codigo="C")
        ciencias_basicas = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        self.agregar_lista_departamental(participacion, self.departamento, 109)
        self.agregar_lista_departamental(participacion, civil, 110)
        lista_basicas = self.agregar_lista_departamental(participacion, ciencias_basicas, 111)
        self.agregar_lista_departamental(otra, self.departamento, 112)

        boletas = _obtener_boletas(self.eleccion)
        filas, errores = _crear_filas_boletas(boletas)

        self.assertEqual(errores, [])
        self.assertEqual(len(boletas), 3)
        self.assertFalse(any(boleta["departamento"] == ciencias_basicas for boleta in boletas))
        filas_azules = [
            fila for fila in filas
            if any(columna and columna["participacion"].pk == participacion.pk for columna in fila["columnas"])
        ]
        self.assertEqual(len(filas_azules), 4)
        for fila in filas_azules:
            self.assertIsNotNone(fila["columnas"][2])
            self.assertEqual(fila["columnas"][3]["puestos"][0]["candidatos"][0].lista_id, lista_basicas.pk)
        filas_verdes = [
            fila for fila in filas
            if any(columna and columna["participacion"].pk == otra.pk for columna in fila["columnas"])
        ]
        self.assertTrue(all(fila["columnas"][3] is None for fila in filas_verdes))
        with patch(
            "apps.reportes.services_boletas_pdf._dibujar_boleta_cuadrante",
            wraps=_dibujar_boleta_cuadrante,
        ) as dibujar:
            contenido = generar_boletas_pdf(self.eleccion)
        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertEqual(
            [llamada.args[1] for llamada in dibujar.call_args_list],
            [columna for fila in filas for columna in fila["columnas"] if columna is not None],
        )
        self.assertTrue(validar_boletas_pdf(self.eleccion).apto)

    def test_docentes_reconoce_puesto_denominado_ciencias_basicas(self):
        boleta = self.crear_boleta_prueba(
            "Docentes", None, "Ciencias Básicas", "Consejero/a",
        )
        filas, errores = _crear_filas_boletas([boleta])

        self.assertEqual(errores, [])
        self.assertEqual([columna is not None for columna in filas[0]["columnas"]], [False, False, False, True])

    def test_docentes_con_solo_ciencias_basicas_y_general_no_crea_departamento_aparte(self):
        docentes = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Docentes"),
        )
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="DOC-BASICAS", eleccion_claustro=docentes,
            numero_lista="11", nombre_lista="Lista Básicas",
        )
        ciencias_basicas = Departamento.objects.create(nombre="Ciencias Basicas", codigo="CB")
        configuracion = EleccionClaustroDepartamento.objects.create(
            eleccion_claustro=docentes, departamento=ciencias_basicas,
        )
        self.agregar_lista_departamental(participacion, ciencias_basicas, 113)
        organo = OrganoElectivo.objects.create(nombre="Consejo Directivo")
        cargo = CargoElectivo.objects.create(organo=organo, nombre="Consejero/a directivo/a")
        puesto = PuestoEleccion.objects.create(
            puesto=cargo, eleccion_claustro=docentes, cantidad_titulares=1, cantidad_suplentes=1,
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion, eleccion_claustro=docentes, puesto_eleccion=puesto,
        )
        Candidato.objects.create(
            lista=lista, elector=self.crear_elector(114, "General", configuracion), cargo=cargo.nombre,
            tipo=Candidato.Tipo.TITULAR, orden=1,
        )

        boletas = _obtener_boletas(self.eleccion)
        filas, errores = _crear_filas_boletas(boletas)

        self.assertEqual(errores, [])
        self.assertEqual(len(boletas), 1)
        self.assertIsNone(boletas[0]["departamento"])
        self.assertEqual(len(filas), 1)
        self.assertEqual([columna is not None for columna in filas[0]["columnas"]], [False, True, False, True])
        self.assertTrue(generar_boletas_pdf(self.eleccion).startswith(b"%PDF"))

    def test_graduados_conserva_ciencias_basicas_en_un_grupo_separado(self):
        graduados = EleccionClaustro.objects.create(
            eleccion=self.eleccion, claustro=Claustro.objects.create(nombre="Graduados"),
        )
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion, codigo_presentacion="GRAD", eleccion_claustro=graduados,
            numero_lista="10", nombre_lista="Lista Azul",
        )
        ciencias_basicas = Departamento.objects.create(nombre="Ciencias Básicas", codigo="Z")
        self.agregar_lista_departamental(participacion, self.departamento, 115)
        lista_basicas = self.agregar_lista_departamental(participacion, ciencias_basicas, 116)

        boletas = _obtener_boletas(self.eleccion)
        filas, errores = _crear_filas_boletas(boletas)

        self.assertEqual(errores, [])
        self.assertEqual(len(boletas), 2)
        fila_basicas = next(fila for fila in filas if fila["columnas"][3] is not None)
        self.assertIsNone(fila_basicas["columnas"][2])
        self.assertEqual(fila_basicas["columnas"][3]["puestos"][0]["candidatos"][0].lista_id, lista_basicas.pk)
        self.assertTrue(all(
            fila["columnas"][3] is None for fila in filas if fila.get("fila_departamental")
        ))

    def test_dasuten_se_imprime_en_fila_independiente_y_no_se_duplica(self):
        boletas = [
            self.crear_boleta_prueba(
                "Estudiantes",
                self.departamento,
                "DASUTeN",
                "Consejero/a",
            ),
            self.crear_boleta_prueba(
                "Estudiantes",
                self.departamento,
                "DASUTeN",
                "Consejero/a",
            ),
        ]

        filas, puestos_sin_categoria = _crear_filas_boletas(boletas)

        self.assertEqual(puestos_sin_categoria, [])
        self.assertEqual(len(filas), 1)
        self.assertTrue(filas[0]["fila_dasuten"])
        self.assertEqual(
            [columna is not None for columna in filas[0]["columnas"]],
            [True, False, False, False],
        )

    def test_puesto_sin_categoria_se_informa_sin_generar_boleta(self):
        boleta = self.crear_boleta_prueba(
            "Estudiantes",
            self.departamento,
            "Otro órgano",
            "Puesto sin categoría",
        )

        filas, puestos_sin_categoria = _crear_filas_boletas([boleta])

        self.assertEqual(filas, [])
        self.assertEqual(puestos_sin_categoria, ["Otro órgano — Puesto sin categoría"])

    def test_boleta_imprime_departamento_configurado_en_el_puesto(self):
        participacion = ParticipacionPartido.objects.create(
            eleccion=self.eleccion,
            codigo_presentacion="DEPARTAMENTO",
            eleccion_claustro=self.eleccion_claustro,
            numero_lista="30",
            nombre_lista="Lista Departamental",
        )
        lista = ListaCandidatos.objects.create(
            participacion=participacion,
            eleccion_claustro=self.eleccion_claustro,
            nombre="Consejo Departamental",
            puesto_eleccion=self.puesto,
        )
        Candidato.objects.create(
            lista=lista,
            elector=self.crear_elector(3, "Carla"),
            cargo=self.cargo.nombre,
            tipo=Candidato.Tipo.TITULAR,
            orden=1,
        )

        boleta = _obtener_boletas(self.eleccion)[0]
        filas, puestos_sin_categoria = _crear_filas_boletas([boleta])

        self.assertEqual(str(boleta["departamento"]), "Sistemas boletas")
        self.assertEqual(puestos_sin_categoria, [])
        self.assertEqual(filas[0]["columnas"][2]["departamento"], self.departamento)
        self.assertIs(filas[1]["columnas"][2], filas[0]["columnas"][2])
        contenido = generar_boletas_pdf(self.eleccion)
        self.assertEqual(contar_paginas_pdf(contenido), 1)

    def test_vista_genera_pdf_descargable_con_permiso_de_eleccion(self):
        self.crear_presentacion(
            codigo="A",
            numero="10",
            nombre="Lista Azul",
            elector=self.crear_elector(1, "Ana"),
        )
        self.client.force_login(self.usuario)

        respuesta = self.client.get(
            reverse("generar-boletas-pdf", args=(self.eleccion.id,)),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn('filename="boletas_', respuesta["Content-Disposition"])
        self.assertTrue(respuesta.content.startswith(b"%PDF"))

    def test_vista_bloquea_generacion_sin_permiso_sobre_la_eleccion(self):
        self.crear_presentacion(
            codigo="A",
            numero="10",
            nombre="Lista Azul",
            elector=self.crear_elector(1, "Ana"),
        )
        usuario = get_user_model().objects.create_user(username="sin-permiso-boletas")
        self.client.force_login(usuario)

        respuesta = self.client.get(
            reverse("generar-boletas-pdf", args=(self.eleccion.id,)),
        )

        self.assertEqual(respuesta.status_code, 403)
