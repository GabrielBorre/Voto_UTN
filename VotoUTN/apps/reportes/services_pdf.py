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
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Image as ImagenPDF
from reportlab.platypus import Paragraph, Table, TableStyle

from apps.asistencia.services import ServicioRegistroParticipacion
from apps.padron.models import RegistroPadron

PAGINA = portrait(legal)
ANCHO_PAGINA, ALTO_PAGINA = PAGINA
MARGEN = 10 * mm
ANCHO_TABLA = ANCHO_PAGINA - 2 * MARGEN
ELECTORES_POR_PAGINA = 15

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
    padrones = RegistroPadron.objects.filter(eleccion=eleccion, activo=True)
    total = padrones.count()
    if total == 0:
        return ValidacionPadronPDF(False, ["La elección no tiene electores cargados en el padrón."])

    sin_sede = padrones.filter(sede__isnull=True).count()
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
        for inicio in range(0, len(electores), ELECTORES_POR_PAGINA):
            lote = electores[inicio: inicio + ELECTORES_POR_PAGINA]
            _dibujar_pagina(canvas_obj, eleccion, mesa, lote, numero_inicial=inicio + 1)
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
            "asignacion_mesa__mesa__turno",
            "asignacion_mesa__mesa__eleccion_claustro_departamento__eleccion_claustro",
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
    return eleccion.fecha_inicio.date()


def _generar_imagen_qr(payload):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=6, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    imagen_buffer = BytesIO()
    imagen.save(imagen_buffer, format="PNG")
    imagen_buffer.seek(0)
    return imagen_buffer


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
    lineas = [
        f"Elección: {eleccion.nombre}",
        f"Fecha de votación: {fecha_votacion.strftime('%d/%m/%Y')}",
        f"Sede: {sede_nombre}    Mesa: {mesa.numero}",
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


def _construir_troquel(eleccion, mesa, registro, alto_fila):
    payload = ServicioRegistroParticipacion.generar_codigo_qr(
        eleccion_id=eleccion.id,
        mesa_numero=mesa.numero,
        identificador_qr=registro.identificador_qr,
    )
    qr_imagen = ImagenPDF(_generar_imagen_qr(payload), width=14 * mm, height=14 * mm)
    fecha_votacion = _fecha_votacion_mesa(eleccion, mesa)

    texto = Table(
        [
            [Paragraph(registro.elector.nombre, ESTILO_TROQUEL)],
            [Paragraph(f"DNI: {registro.elector.dni}", ESTILO_TROQUEL)],
            [Paragraph(f"Fecha: {fecha_votacion.strftime('%d/%m/%Y')}", ESTILO_TROQUEL)],
            [_construir_espacio_firma("Autoridad de mesa", COL_TROQUEL - 20 * mm, alto_fila - 16 * mm)],
        ],
        colWidths=[COL_TROQUEL - 16 * mm],
        rowHeights=[2 * mm, 2 * mm, 2 * mm, alto_fila - 9 * mm],
    )
    texto.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
    ]))

    contenedor = Table(
        [[qr_imagen, texto]],
        colWidths=[15 * mm, COL_TROQUEL - 15 * mm],
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
            Paragraph(registro.elector.nombre, ESTILO_CELDA),
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
        ("BACKGROUND", (4, 1), (4, -1), colors.HexColor("#f5f5f5")),
        ("LINEBEFORE", (4, 0), (4, -1), 1.2, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabla


def _dibujar_pagina(c, eleccion, mesa, lote, numero_inicial):
    y_tabla = _dibujar_encabezado(c, eleccion, mesa)
    alto_encabezado = 8 * mm
    alto_fila = (y_tabla - MARGEN - alto_encabezado) / ELECTORES_POR_PAGINA
    tabla = _construir_tabla(eleccion, mesa, lote, numero_inicial, alto_fila)
    _, alto = tabla.wrapOn(c, ANCHO_TABLA, y_tabla - MARGEN)
    tabla.drawOn(c, MARGEN, y_tabla - alto)
