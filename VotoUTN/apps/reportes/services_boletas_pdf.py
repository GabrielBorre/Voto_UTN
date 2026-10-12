"""Generación de boletas electorales imprimibles a partir de las candidaturas."""
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.text import slugify

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import legal, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.partidos.models import Candidato, ListaCandidatos


PAGINA = portrait(legal)
MARGEN = 12 * mm
POSICION_LINEA_ENCABEZADO = MARGEN + 21 * mm
MARGEN_SUPERIOR_CONTENIDO = POSICION_LINEA_ENCABEZADO + 5 * mm
LOGO_UTN = Path(settings.BASE_DIR) / "static" / "img" / "logo-utn.jpg"
ORDEN_TIPO_CANDIDATO = {
    Candidato.Tipo.TITULAR: 0,
    Candidato.Tipo.SUPLENTE: 1,
}


@dataclass(frozen=True)
class ValidacionBoletasPDF:
    apto: bool
    cantidad_boletas: int = 0
    motivos: list[str] = field(default_factory=list)


def _obtener_boletas(eleccion):
    listas = (
        ListaCandidatos.objects.filter(
            participacion__eleccion=eleccion,
            participacion__activa=True,
            activa=True,
            candidatos__activo=True,
        )
        .distinct()
        .select_related(
            "participacion__eleccion_claustro__claustro",
            "participacion__partido",
            "eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
            "puesto_eleccion__puesto__organo",
            "puesto_eleccion__eleccion_claustro_departamento__departamento",
        )
        .prefetch_related(
            Prefetch(
                "candidatos",
                queryset=Candidato.objects.filter(activo=True)
                .select_related("elector")
                .order_by("tipo", "orden"),
            ),
        )
        .order_by(
            "eleccion_claustro__claustro__nombre",
            "eleccion_claustro_departamento__departamento__nombre",
            "participacion__numero_lista",
            "participacion__nombre_lista",
            "puesto_eleccion__puesto__organo__nombre",
            "puesto_eleccion__puesto__nombre",
            "nombre",
        )
    )

    grupos = {}
    for lista in listas:
        participacion = lista.participacion
        alcance = lista.eleccion_claustro
        alcance_departamental = (
            lista.puesto_eleccion.eleccion_claustro_departamento
            if lista.puesto_eleccion_id
            and lista.puesto_eleccion.eleccion_claustro_departamento_id
            else lista.eleccion_claustro_departamento
        )
        clave = (
            participacion.pk,
            alcance.pk,
            alcance_departamental.pk if alcance_departamental else None,
        )
        grupo = grupos.setdefault(
            clave,
            {
                "participacion": participacion,
                "claustro": alcance.claustro,
                "departamento": (
                    alcance_departamental.departamento
                    if alcance_departamental
                    else None
                ),
                "puestos": {},
            },
        )
        puesto_id = lista.puesto_eleccion_id or ("lista", lista.pk)
        puesto = grupo["puestos"].setdefault(
            puesto_id,
            {
                "organo": (
                    lista.puesto_eleccion.puesto.organo.nombre
                    if lista.puesto_eleccion_id
                    else ""
                ),
                "nombre": (
                    lista.puesto_eleccion.puesto.nombre
                    if lista.puesto_eleccion_id
                    else lista.nombre
                ),
                "candidatos": [],
            },
        )
        for candidato in lista.candidatos.all():
            nombre = (
                candidato.elector.nombre_completo
                if candidato.elector_id
                else candidato.nombre
            ).strip()
            if nombre:
                puesto["candidatos"].append(candidato)

    boletas = []
    for grupo in grupos.values():
        grupo["puestos"] = [
            puesto
            for puesto in grupo["puestos"].values()
            if puesto["candidatos"]
        ]
        if not grupo["puestos"]:
            continue
        for puesto in grupo["puestos"]:
            puesto["candidatos"].sort(
                key=lambda candidato: (
                    ORDEN_TIPO_CANDIDATO.get(candidato.tipo, 2),
                    candidato.orden,
                )
            )
        boletas.append(grupo)
    return boletas


def validar_boletas_pdf(eleccion) -> ValidacionBoletasPDF:
    cantidad = len(_obtener_boletas(eleccion))
    if cantidad == 0:
        return ValidacionBoletasPDF(
            apto=False,
            motivos=["La elección no tiene listas activas con candidatos para generar boletas."],
        )
    return ValidacionBoletasPDF(apto=True, cantidad_boletas=cantidad)


def generar_nombre_archivo_boletas(eleccion) -> str:
    fecha = timezone.now().strftime("%Y%m%d")
    slug = slugify(eleccion.nombre) or f"eleccion-{eleccion.id}"
    return f"boletas_{slug}_{fecha}.pdf"


def _dibujar_encabezado(canvas, documento, eleccion):
    ancho, alto = PAGINA
    canvas.saveState()
    canvas.drawImage(
        ImageReader(str(LOGO_UTN)),
        MARGEN,
        alto - MARGEN - 18 * mm,
        width=82 * mm,
        height=18 * mm,
        preserveAspectRatio=True,
        anchor="sw",
        mask="auto",
    )
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(ancho - MARGEN, alto - MARGEN - 4 * mm, eleccion.nombre[:90])
    canvas.drawRightString(
        ancho - MARGEN,
        alto - MARGEN - 9 * mm,
        f"Generado: {timezone.localtime().strftime('%d/%m/%Y %H:%M')}",
    )
    canvas.setLineWidth(0.8)
    canvas.line(MARGEN, alto - MARGEN - 21 * mm, ancho - MARGEN, alto - MARGEN - 21 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(ancho - MARGEN, 7 * mm, f"Página {documento.page}")
    canvas.restoreState()


def _construir_contenido_boleta(boleta, estilos, ancho):
    participacion = boleta["participacion"]
    estilo_centrado = estilos["boleta_titulo"]
    elementos = [
        Paragraph("BOLETA ELECTORAL", estilo_centrado),
        Spacer(1, 4 * mm),
    ]

    alcance = [f"Claustro: {escape(str(boleta['claustro']))}"]
    if boleta["departamento"] is not None:
        alcance.append(f"Departamento: {escape(str(boleta['departamento']))}")
    alcance.append(f"Número de lista: {escape(participacion.numero_lista)}")
    if participacion.nombre_lista:
        alcance.append(f"Lista: {escape(participacion.nombre_lista)}")

    tabla_presentacion = Table(
        [[Paragraph("<br/>".join(alcance), estilos["presentacion"])]],
        colWidths=[ancho],
    )
    tabla_presentacion.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2f7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
    ]))
    elementos.extend((tabla_presentacion, Spacer(1, 5 * mm)))

    for puesto in boleta["puestos"]:
        titulo = " — ".join(
            parte for parte in (puesto["organo"], puesto["nombre"]) if parte
        )
        elementos.append(Paragraph(escape(titulo), estilos["puesto"]))
        filas = [["Orden", "Tipo", "Apellido y nombre"]]
        for candidato in puesto["candidatos"]:
            nombre = (
                candidato.elector.nombre_completo
                if candidato.elector_id
                else candidato.nombre
            ).strip()
            filas.append([
                str(candidato.orden),
                escape(candidato.get_tipo_display()),
                Paragraph(escape(nombre), estilos["candidato"]),
            ])
        tabla_candidatos = Table(
            filas,
            colWidths=[20 * mm, 32 * mm, ancho - 52 * mm],
            repeatRows=1,
        )
        tabla_candidatos.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ]))
        elementos.extend((tabla_candidatos, Spacer(1, 4 * mm)))
    return elementos


def generar_boletas_pdf(eleccion) -> bytes:
    boletas = _obtener_boletas(eleccion)
    if not boletas:
        raise ValueError(
            "La elección no tiene listas activas con candidatos para generar boletas."
        )

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=PAGINA,
        rightMargin=MARGEN,
        leftMargin=MARGEN,
        topMargin=MARGEN_SUPERIOR_CONTENIDO,
        bottomMargin=13 * mm,
        title=f"Boletas electorales - {eleccion.nombre}",
        author="Junta Electoral UTN",
    )
    estilos_base = getSampleStyleSheet()
    estilos = {
        "boleta_titulo": ParagraphStyle(
            "boleta_titulo",
            parent=estilos_base["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            textColor=colors.black,
        ),
        "presentacion": ParagraphStyle(
            "boleta_presentacion",
            parent=estilos_base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
        ),
        "puesto": ParagraphStyle(
            "boleta_puesto",
            parent=estilos_base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "candidato": ParagraphStyle(
            "boleta_candidato",
            parent=estilos_base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
        ),
    }
    ancho = PAGINA[0] - 2 * MARGEN
    elementos = []
    for indice, boleta in enumerate(boletas):
        if indice:
            elementos.append(PageBreak())
        elementos.extend(_construir_contenido_boleta(boleta, estilos, ancho))

    documento.build(
        elementos,
        onFirstPage=lambda canvas, doc: _dibujar_encabezado(canvas, doc, eleccion),
        onLaterPages=lambda canvas, doc: _dibujar_encabezado(canvas, doc, eleccion),
    )
    return buffer.getvalue()
