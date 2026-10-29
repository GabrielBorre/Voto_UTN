"""Generacion del padron electoral imprimible en PDF (hoja Oficio/Legal)."""
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import legal, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.shapes import Drawing, Path as Trazado, Rect
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, Table, TableStyle

from apps.asistencia.services import ServicioRegistroParticipacion
from apps.elecciones.models import Eleccion
from apps.padron.models import RegistroPadron

PAGINA = portrait(legal)
ANCHO_PAGINA, ALTO_PAGINA = PAGINA
MARGEN = 10 * mm
ANCHO_TABLA = ANCHO_PAGINA - 2 * MARGEN
ELECTORES_POR_PAGINA = 15
LADO_QR_ELECTOR = 22 * mm
ANCHO_COLUMNA_QR = 19 * mm

COL_ORDEN = 12 * mm
COL_DNI = 24 * mm
COL_NOMBRE = 62 * mm
COL_FIRMA = 48 * mm
COL_TROQUEL = ANCHO_TABLA - (COL_ORDEN + COL_DNI + COL_NOMBRE + COL_FIRMA)

ESTILO_CELDA = ParagraphStyle("padron_celda", fontName="Helvetica", fontSize=8, leading=9.5)
ESTILO_TROQUEL = ParagraphStyle("padron_troquel", fontName="Helvetica", fontSize=5.5, leading=9, alignment=TA_RIGHT)
ESTILO_FIRMA = ParagraphStyle("padron_firma", fontName="Helvetica", fontSize=6.5, leading=10, alignment=TA_CENTER)
LOGO_UTN = Path(settings.BASE_DIR) / "static" / "img" / "logo-utn.jpg"


@dataclass(frozen=True)
class ValidacionPadronPDF:
    apto: bool
    motivos: list = field(default_factory=list)


def validar_padron_para_pdf(eleccion) -> ValidacionPadronPDF:
    motivos = []
    if eleccion.estado != Eleccion.Estado.EN_CURSO:
        motivos.append("El padrón imprimible solo se puede generar cuando la elección está en curso.")
    padrones = RegistroPadron.objects.filter(eleccion=eleccion, activo=True)
    total = padrones.count()
    if total == 0:
        return ValidacionPadronPDF(False, motivos + ["La elección no tiene electores cargados en el padrón."])

    sin_sede = padrones.filter(asignacion_mesa__mesa__sede__isnull=True).count()
    if sin_sede:
        motivos.append(f"Hay {sin_sede} elector(es) sin sede asignada.")

    sin_mesa = padrones.filter(asignacion_mesa__isnull=True).count()
    if sin_mesa:
        motivos.append(f"Hay {sin_mesa} elector(es) sin mesa asignada.")

    sin_qr = padrones.filter(identificador_qr="").count()
    if sin_qr:
        motivos.append(f"Hay {sin_qr} elector(es) sin identificador QR generado.")

    return ValidacionPadronPDF(apto=not motivos, motivos=motivos)


def generar_nombre_archivo_padron(eleccion) -> str:
    fecha = timezone.now().strftime("%Y%m%d")
    slug = slugify(eleccion.nombre) or f"eleccion-{eleccion.id}"
    return f"padron_{slug}_{fecha}.pdf"


def generar_padron_pdf(eleccion) -> bytes:
    validacion = validar_padron_para_pdf(eleccion)
    if not validacion.apto:
        raise ValueError(" ".join(validacion.motivos))

    grupos = _agrupar_padrones_por_mesa(eleccion)
    buffer = BytesIO()
    canvas_obj = pdfcanvas.Canvas(buffer, pagesize=PAGINA)

    for grupo in grupos:
        mesa = grupo["mesa"]
        electores = grupo["padrones"]
        total_paginas = -(-len(electores) // ELECTORES_POR_PAGINA)
        _dibujar_caratula(canvas_obj, eleccion, mesa)
        canvas_obj.showPage()
        for pagina, inicio in enumerate(range(0, len(electores), ELECTORES_POR_PAGINA), start=1):
            lote = electores[inicio: inicio + ELECTORES_POR_PAGINA]
            _dibujar_pagina(canvas_obj, eleccion, mesa, lote, numero_inicial=inicio + 1)
            _dibujar_pie_pagina(canvas_obj, pagina, total_paginas)
            canvas_obj.showPage()

    canvas_obj.save()
    return buffer.getvalue()


def _agrupar_padrones_por_mesa(eleccion):
    padrones = (
        RegistroPadron.objects.filter(eleccion=eleccion, activo=True)
        .select_related(
            "elector",
            "sede",
            "asignacion_mesa__mesa__sede",
            "asignacion_mesa__mesa__eleccion_claustro_departamento__eleccion_claustro",
            "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento",
        )
        .order_by("elector__nombre", "elector__legajo")
    )
    grupos = {}
    for padron in padrones:
        mesa = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
        if mesa is None:
            continue
        grupos.setdefault(mesa.id, {"mesa": mesa, "padrones": []})["padrones"].append(padron)

    return sorted(
        grupos.values(),
        key=lambda grupo: (grupo["mesa"].sede.nombre if grupo["mesa"].sede_id else "", grupo["mesa"].numero),
    )


def _fecha_votacion_mesa(eleccion, mesa):
    configuracion = mesa.eleccion_claustro_departamento
    if configuracion and configuracion.eleccion_claustro.fecha_votacion:
        return configuracion.eleccion_claustro.fecha_votacion
    return eleccion.fecha_inicio


def _generar_qr_vectorial(payload, lado):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    matriz = qr.get_matrix()
    modulo = lado / len(matriz)
    dibujo = Drawing(lado, lado)
    dibujo.add(Rect(0, 0, lado, lado, fillColor=colors.white, strokeColor=None))
    trazado = Trazado(fillColor=colors.black, strokeColor=None)
    for fila, modulos in enumerate(matriz):
        for columna, oscuro in enumerate(modulos):
            if oscuro:
                x = columna * modulo
                y = lado - (fila + 1) * modulo
                trazado.moveTo(x, y)
                trazado.lineTo(x + modulo, y)
                trazado.lineTo(x + modulo, y + modulo)
                trazado.lineTo(x, y + modulo)
                trazado.closePath()
    dibujo.add(trazado)
    return dibujo


def _construir_espacio_firma(rotulo, ancho, alto):
    espacio_rotulo = 4 * mm
    firma = Table(
        [[""], [Paragraph(rotulo, ESTILO_FIRMA)]],
        colWidths=[ancho],
        rowHeights=[max(alto - espacio_rotulo, 1 * mm), espacio_rotulo],
    )
    firma.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (0, 0), 0.7, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    return firma


def _dibujar_encabezado(c, eleccion, mesa):
    y = ALTO_PAGINA - MARGEN

    c.drawImage(
        ImageReader(str(LOGO_UTN)),
        MARGEN,
        y - 18 * mm,
        width=82 * mm,
        height=18 * mm,
        preserveAspectRatio=True,
        anchor="sw",
        mask="auto",
    )

    fecha_votacion = _fecha_votacion_mesa(eleccion, mesa)
    sede_nombre = mesa.sede.nombre if mesa.sede_id else "Sin sede"
    configuracion = mesa.eleccion_claustro_departamento
    departamento = configuracion.departamento if configuracion and configuracion.departamento_id else None
    lineas = [
        f"Elección: {eleccion.nombre}",
        f"Departamento: {departamento.nombre if departamento else 'Sin departamento'}",
        f"Fecha de votación: {fecha_votacion.strftime('%d/%m/%Y')}",
        f"Sede: {sede_nombre}    Mesa: {mesa.codigo}",
    ]
    c.setFont("Helvetica", 7.5)
    y_info = y - 4 * mm
    for linea in lineas:
        c.drawRightString(ANCHO_PAGINA - MARGEN, y_info, linea)
        y_info -= 3.6 * mm

    linea_y = y - 20 * mm
    c.setLineWidth(0.8)
    c.line(MARGEN, linea_y, ANCHO_PAGINA - MARGEN, linea_y)
    return linea_y - 3 * mm


def _formatear_apellido_y_nombre(elector):
    if elector.apellido:
        return f"{elector.apellido}, {elector.nombre}"
    return elector.nombre


def _construir_troquel(eleccion, mesa, registro, alto_fila):
    payload = ServicioRegistroParticipacion.generar_codigo_qr(
        eleccion_id=eleccion.id,
        mesa_numero=mesa.numero,
        identificador_qr=registro.identificador_qr,
    )
    qr_imagen = _generar_qr_vectorial(payload, LADO_QR_ELECTOR)
    fecha_votacion = _fecha_votacion_mesa(eleccion, mesa)
    ancho_texto = COL_TROQUEL - ANCHO_COLUMNA_QR - 2
    firma_autoridad = _construir_espacio_firma(
        "Autoridad de mesa", ancho_texto - 2 - 4 * mm, alto_fila - 16 * mm,
    )
    firma_autoridad.hAlign = "LEFT"

    texto = Table(
        [
            [Paragraph(_formatear_apellido_y_nombre(registro.elector), ESTILO_TROQUEL)],
            [Paragraph(f"DNI: {registro.elector.dni}", ESTILO_TROQUEL)],
            [Paragraph(f"Fecha: {fecha_votacion.strftime('%d/%m/%Y')}", ESTILO_TROQUEL)],
            [firma_autoridad],
        ],
        colWidths=[ancho_texto],
        rowHeights=[2 * mm, 2 * mm, 2 * mm, alto_fila - 9 * mm],
    )
    texto.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 3), (0, 3), 1 + 2 * mm),
        ("RIGHTPADDING", (0, 3), (0, 3), 1 + 2 * mm),
    ]))

    contenedor = Table(
        [[qr_imagen, texto]],
        colWidths=[ANCHO_COLUMNA_QR, COL_TROQUEL - ANCHO_COLUMNA_QR],
        rowHeights=[alto_fila],
    )
    contenedor.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return contenedor


def _construir_tabla(eleccion, mesa, lote, numero_inicial, alto_fila):
    encabezados = ["N.\u00ba", "DNI", "Apellido y nombre", "Firma", "Comprobante de emisión de voto"]
    filas = [encabezados]
    for offset, registro in enumerate(lote):
        numero_orden = numero_inicial + offset
        filas.append([
            str(numero_orden),
            registro.elector.dni,
            Paragraph(_formatear_apellido_y_nombre(registro.elector), ESTILO_CELDA),
            _construir_espacio_firma("Firma del votante", COL_FIRMA - 12, alto_fila),
            _construir_troquel(eleccion, mesa, registro, alto_fila),
        ])

    tabla = Table(
        filas,
        colWidths=[COL_ORDEN, COL_DNI, COL_NOMBRE, COL_FIRMA, COL_TROQUEL],
        rowHeights=[8 * mm] + [alto_fila] * len(lote),
        repeatRows=1,
    )
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("BACKGROUND", (4, 1), (4, -1), colors.white),
        ("LINEBEFORE", (4, 0), (4, -1), 1.2, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (4, 1), (4, -1), 0),
        ("RIGHTPADDING", (4, 1), (4, -1), 0),
        ("TOPPADDING", (4, 1), (4, -1), 0),
        ("BOTTOMPADDING", (4, 1), (4, -1), 0),
    ]))
    return tabla


def _dibujar_caratula(c, eleccion, mesa):
    y = _dibujar_encabezado(c, eleccion, mesa)
    centro = ANCHO_PAGINA / 2
    configuracion = mesa.eleccion_claustro_departamento
    departamento = configuracion.departamento if configuracion and configuracion.departamento_id else None

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(centro, y - 22 * mm, "INFORMACIÓN DE MESA")

    c.setFont("Helvetica", 13)
    y_dato = y - 40 * mm
    datos = [
        f"Elección: {eleccion.nombre}",
        f"Fecha de votación: {_fecha_votacion_mesa(eleccion, mesa).strftime('%d/%m/%Y')}",
        f"Sede: {mesa.sede.nombre if mesa.sede_id else 'Sin sede'}",
        f"Departamento: {departamento.nombre if departamento else 'Sin departamento'}",
    ]
    for linea in datos:
        c.drawCentredString(centro, y_dato, linea)
        y_dato -= 8 * mm

    c.setFont("Helvetica", 12)
    c.drawCentredString(centro, y_dato - 10 * mm, "Código de mesa")
    c.setFont("Helvetica-Bold", 44)
    c.drawCentredString(centro, y_dato - 26 * mm, mesa.codigo)

    lado_qr = 90 * mm
    y_qr = y_dato - 36 * mm - lado_qr
    payload = ServicioRegistroParticipacion.generar_codigo_qr_mesa(eleccion_id=eleccion.id, mesa_numero=mesa.numero)
    _generar_qr_vectorial(payload, lado_qr).drawOn(c, centro - lado_qr / 2, y_qr)
    c.setFont("Helvetica", 10)
    c.drawCentredString(centro, y_qr - 6 * mm, "Escanee este código para comenzar el registro de la mesa")


def _dibujar_pie_pagina(c, pagina, total):
    c.setFont("Helvetica", 8)
    c.drawRightString(ANCHO_PAGINA - MARGEN, 5 * mm, f"Página {pagina} de {total}")


def _dibujar_pagina(c, eleccion, mesa, lote, numero_inicial):
    y_tabla = _dibujar_encabezado(c, eleccion, mesa)
    alto_encabezado = 8 * mm
    alto_fila = (y_tabla - MARGEN - alto_encabezado) / ELECTORES_POR_PAGINA
    tabla = _construir_tabla(eleccion, mesa, lote, numero_inicial, alto_fila)
    _, alto = tabla.wrapOn(c, ANCHO_TABLA, y_tabla - MARGEN)
    tabla.drawOn(c, MARGEN, y_tabla - alto)
