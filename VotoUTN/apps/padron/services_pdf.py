from html import escape
from io import BytesIO

from django.utils import timezone
from django.utils.text import slugify
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import legal, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generar_padron_claustro_pdf(eleccion_claustro, registros):
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(legal),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Padrón de {eleccion_claustro.claustro}",
        author="Voto UTN",
    )
    estilos = getSampleStyleSheet()
    estilo_titulo = estilos["Heading2"]
    estilo_celda = ParagraphStyle(
        "CeldaPadronClaustro",
        parent=estilos["BodyText"],
        fontName="Courier",
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    estilo_encabezado = ParagraphStyle(
        "EncabezadoPadronClaustro",
        parent=estilo_celda,
        fontName="Courier-Bold",
    )
    datos = [[Paragraph(escape(texto), estilo_encabezado) for texto in (
        "APELLIDO/s y NOMBRE/s", "NRO. LEGAJO", "TIPO DOCUMENTO", "NRO. DOCUMENTO", "ESPECIALIDAD",
    )]]
    for registro in registros:
        elector = registro.elector
        apellido_nombre = f"{elector.apellido.upper()}, {elector.nombre}" if elector.apellido else elector.nombre
        datos.append([
            Paragraph(escape(apellido_nombre), estilo_celda),
            Paragraph(escape(elector.legajo), estilo_celda),
            Paragraph(escape(elector.tipo_documento.upper()), estilo_celda),
            Paragraph(escape(elector.dni), estilo_celda),
            Paragraph(escape(str(registro.eleccion_claustro_departamento.departamento)), estilo_celda),
        ])

    ancho_util = landscape(legal)[0] - 24 * mm
    tabla = Table(
        datos,
        colWidths=(ancho_util * 0.34, ancho_util * 0.13, ancho_util * 0.16, ancho_util * 0.16, ancho_util * 0.21),
        repeatRows=1,
        hAlign="LEFT",
    )
    tabla.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, 0), 1, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elementos = [
        Paragraph(f"Padrón · {escape(str(eleccion_claustro.claustro))}", estilo_titulo),
        Paragraph(f"{escape(eleccion_claustro.eleccion.nombre)} · Exportado el {timezone.localdate():%d/%m/%Y}", estilos["Normal"]),
        Spacer(1, 5 * mm),
        tabla,
    ]
    documento.build(elementos)
    return buffer.getvalue()


def nombre_archivo_padron_claustro_pdf(eleccion_claustro):
    claustro = slugify(str(eleccion_claustro.claustro)) or f"claustro-{eleccion_claustro.id}"
    return f"padron_{claustro}_{eleccion_claustro.eleccion_id}.pdf"
