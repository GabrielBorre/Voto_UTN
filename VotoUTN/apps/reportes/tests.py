import re
from io import BytesIO
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import make_aware
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from apps.asistencia.services import ServicioRegistroParticipacion

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionSede,
    EleccionClaustroTurno,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import EmisionPadronImprimible, Elector, RegistroPadron
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
    MARGEN_SUPERIOR_CONTENIDO,
    POSICION_LINEA_ENCABEZADO,
    _construir_contenido_boleta,
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


class PadronPDFTests(TestCase):
    def setUp(self):
        inicio = make_aware(datetime(2026, 8, 3, 8))
        self.eleccion = Eleccion.objects.create(
            nombre="Eleccion Oficio", fecha_inicio=inicio, fecha_fin=inicio + timedelta(hours=8),
            estado=Eleccion.Estado.EN_CURSO,
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
                sede=sede_asignada,
            )
            if mesa_asignada is not None:
                AsignacionMesa.objects.create(registro_padron=registro, mesa=mesa_asignada)
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

    def test_vista_genera_pdf_descargable(self):
        self.crear_electores(3)
        self.client.login(username="admin-reportes", password="clave")

        respuesta = self.client.post(reverse("generar-padron-pdf", args=(self.eleccion.id,)))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        self.assertIn('filename="padron_', respuesta["Content-Disposition"])
        self.assertTrue(EmisionPadronImprimible.objects.filter(eleccion_claustro=self.eleccion_claustro, estado="vigente").exists())
        self.assertTrue(RegistroPadron.objects.filter(eleccion=self.eleccion, qr_generado_en__isnull=False).exists())

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
        self.organo = OrganoElectivo.objects.create(nombre="Consejo de boletas")
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

    def crear_elector(self, indice, nombre):
        elector = Elector.objects.create(
            legajo=f"B{indice:05d}",
            nombre=nombre,
            apellido="Candidata",
            dni=f"4{indice:07d}",
        )
        RegistroPadron.objects.create(
            elector=elector,
            eleccion=self.eleccion,
            eleccion_claustro_departamento=self.configuracion,
        )
        return elector

    def test_validacion_indica_cuando_no_hay_candidaturas_activas(self):
        validacion = validar_boletas_pdf(self.eleccion)

        self.assertFalse(validacion.apto)
        self.assertEqual(validacion.cantidad_boletas, 0)
        self.assertTrue(validacion.motivos)

    def test_titulo_comienza_debajo_de_la_linea_del_encabezado(self):
        self.assertGreater(
            MARGEN_SUPERIOR_CONTENIDO,
            POSICION_LINEA_ENCABEZADO,
        )

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
        self.assertEqual(validacion.cantidad_boletas, 2)
        self.assertTrue(contenido.startswith(b"%PDF"))
        self.assertEqual(contar_paginas_pdf(contenido), 2)

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
        contenido = _construir_contenido_boleta(
            boleta,
            {
                "boleta_titulo": getSampleStyleSheet()["Title"],
                "presentacion": getSampleStyleSheet()["Normal"],
                "puesto": getSampleStyleSheet()["Heading2"],
                "candidato": getSampleStyleSheet()["Normal"],
            },
            500,
        )

        self.assertEqual(str(boleta["departamento"]), "Sistemas boletas")
        self.assertIn(
            "Departamento: Sistemas boletas",
            contenido[2]._cellvalues[0][0].text,
        )

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
