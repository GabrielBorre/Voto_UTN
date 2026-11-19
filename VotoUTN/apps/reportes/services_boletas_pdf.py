"""Generación de boletas electorales imprimibles a partir de las candidaturas."""
from dataclasses import dataclass, field
from io import BytesIO
from xml.sax.saxutils import escape

from django.db.models import Prefetch
from django.utils import timezone
from django.utils.text import slugify

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, legal
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from apps.partidos.models import Candidato, ListaCandidatos


PAGINA = landscape(legal)
MARGEN = 6 * mm
ANCHO_CUADRANTES = 4
FILAS_POR_PAGINA = 2
RELLENO_MARCO_PDF_PT = 6
CATEGORIAS_BOLETA = (
    "superior",
    "directivo",
    "departamental",
    "ciencias_basicas",
)
ETIQUETAS_CATEGORIA = {
    "superior": "CONSEJO SUPERIOR",
    "directivo": "CONSEJO DIRECTIVO",
    "departamental": "CONSEJO DEPARTAMENTAL",
    "ciencias_basicas": "CIENCIAS BÁSICAS",
    "dasuten": "DASUTeN",
}
ORDEN_TIPO_CANDIDATO = {
    Candidato.Tipo.TITULAR: 0,
    Candidato.Tipo.SUPLENTE: 1,
}


class NumeroListaBoleta(Flowable):
    def __init__(self, numero, ancho, escala=1):
        super().__init__()
        self.numero = str(numero)
        self.width = ancho
        self.height = 12 * mm * escala
        self.escala = escala

    def draw(self):
        self.canv.saveState()
        self.canv.setLineWidth(1.2)
        ancho_ovalo = min(24 * mm * self.escala, self.width - 2 * mm)
        alto_ovalo = 9 * mm * self.escala
        x_ovalo = (self.width - ancho_ovalo) / 2
        y_ovalo = (self.height - alto_ovalo) / 2
        self.canv.ellipse(
            x_ovalo,
            y_ovalo,
            x_ovalo + ancho_ovalo,
            y_ovalo + alto_ovalo,
        )
        self.canv.setFont("Helvetica-Bold", 11 * self.escala)
        self.canv.drawCentredString(
            self.width / 2,
            y_ovalo + 2.7 * mm * self.escala,
            self.numero,
        )
        self.canv.restoreState()


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

    grupos_departamentales = {}
    grupos_transversales = {}
    for lista in listas:
        participacion = lista.participacion
        alcance = lista.eleccion_claustro
        alcance_departamental = (
            lista.puesto_eleccion.eleccion_claustro_departamento
            if lista.puesto_eleccion_id
            and lista.puesto_eleccion.eleccion_claustro_departamento_id
            else lista.eleccion_claustro_departamento
        )
        clave_lista = (
            participacion.eleccion_id,
            participacion.numero_lista,
            participacion.nombre_lista.strip().casefold(),
            alcance.claustro_id,
        )
        if alcance_departamental is None:
            grupo = grupos_transversales.setdefault(
                clave_lista,
                {
                    "participacion": participacion,
                    "clave_lista": clave_lista,
                    "claustros": set(),
                    "departamento": None,
                    "listas": [],
                    "puestos": {},
                },
            )
        else:
            clave = (*clave_lista, alcance_departamental.departamento_id)
            grupo = grupos_departamentales.setdefault(
                clave,
                {
                    "participacion": participacion,
                    "clave_lista": clave_lista,
                    "claustros": set(),
                    "departamento": alcance_departamental.departamento,
                    "listas": [],
                    "puestos": {},
                },
            )
        grupo["listas"].append(lista)

    def agregar_lista(grupo, lista):
        alcance = lista.eleccion_claustro
        grupo["claustros"].add(str(alcance.claustro))
        puesto_id = lista.puesto_eleccion_id or ("lista", lista.pk)
        puesto = grupo["puestos"].setdefault(
            puesto_id,
            {
                "organo": (
                    lista.puesto_eleccion.puesto.organo.nombre
                    if lista.puesto_eleccion_id
                    else ""
                ),
                "claustro": str(alcance.claustro),
                "nombre": (
                    lista.puesto_eleccion.puesto.nombre
                    if lista.puesto_eleccion_id
                    else lista.nombre
                ),
                "departamento": (
                    lista.puesto_eleccion.eleccion_claustro_departamento.departamento
                    if lista.puesto_eleccion_id
                    and lista.puesto_eleccion.eleccion_claustro_departamento_id
                    else (
                        lista.eleccion_claustro_departamento.departamento
                        if lista.eleccion_claustro_departamento_id
                        else None
                    )
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

    grupos_boletas = []
    identidades_con_alcance_departamental = set()
    listas_basicas_compartidas = {}
    for clave, grupo in grupos_departamentales.items():
        if (
            _es_ciencias_basicas(grupo["departamento"])
            and _comparte_basicas_por_departamento(grupo["participacion"].eleccion_claustro.claustro.nombre)
        ):
            listas_basicas_compartidas.setdefault(clave[:-1], []).extend(grupo["listas"])

    for clave, grupo in grupos_departamentales.items():
        clave_lista = clave[:-1]
        if (
            clave_lista in listas_basicas_compartidas
            and _es_ciencias_basicas(grupo["departamento"])
        ):
            continue
        identidades_con_alcance_departamental.add(clave_lista)
        for lista in grupo["listas"]:
            agregar_lista(grupo, lista)
        for lista in listas_basicas_compartidas.get(clave_lista, ()):
            agregar_lista(grupo, lista)
        grupo_transversal = grupos_transversales.get(clave_lista)
        if grupo_transversal:
            for lista in grupo_transversal["listas"]:
                agregar_lista(grupo, lista)
        grupos_boletas.append(grupo)

    for clave_lista, listas_basicas in listas_basicas_compartidas.items():
        if clave_lista in identidades_con_alcance_departamental:
            continue
        grupo = {
            "participacion": listas_basicas[0].participacion,
            "clave_lista": clave_lista,
            "claustros": set(),
            "departamento": None,
            "listas": [],
            "puestos": {},
        }
        for lista in listas_basicas:
            agregar_lista(grupo, lista)
        grupo_transversal = grupos_transversales.get(clave_lista)
        if grupo_transversal:
            for lista in grupo_transversal["listas"]:
                agregar_lista(grupo, lista)
        grupos_boletas.append(grupo)
        identidades_con_alcance_departamental.add(clave_lista)

    for clave_lista, grupo in grupos_transversales.items():
        if clave_lista not in identidades_con_alcance_departamental:
            for lista in grupo["listas"]:
                agregar_lista(grupo, lista)
            grupos_boletas.append(grupo)

    boletas = []
    for grupo in grupos_boletas:
        grupo["claustros"] = sorted(grupo["claustros"])
        grupo.pop("listas")
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


def _es_ciencias_basicas(departamento):
    return bool(
        departamento
        and (
            departamento.codigo.casefold() == "z"
            or slugify(departamento.nombre) == "ciencias-basicas"
        )
    )


def _comparte_basicas_por_departamento(claustro):
    nombre = slugify(claustro)
    return "estudiante" in nombre or "docente" in nombre


def _clasificar_puesto(boleta, puesto):
    claustro = slugify(" ".join(boleta["claustros"]))
    departamento_especial = _es_ciencias_basicas(
        puesto.get("departamento") or boleta["departamento"]
    )
    nombre = slugify(f"{puesto['organo']} {puesto['nombre']}")

    if "dasuten" in nombre:
        return "dasuten"
    if "superior" in nombre:
        return "superior"
    if "directivo" in nombre:
        return "directivo"
    if "ciencias-basicas" in nombre and (
        _comparte_basicas_por_departamento(claustro) or "graduado" in claustro
    ):
        return "ciencias_basicas"
    if "departamental" in nombre:
        if departamento_especial and (
            _comparte_basicas_por_departamento(claustro) or "graduado" in claustro
        ):
            return "ciencias_basicas"
        return "departamental"
    return None


def _crear_filas_boletas(boletas):
    filas = []
    puestos_sin_categoria = set()
    listas_dasuten_emitidas = set()

    for boleta in boletas:
        puestos_por_categoria = {categoria: [] for categoria in CATEGORIAS_BOLETA}
        puestos_dasuten = []
        for puesto in boleta["puestos"]:
            categoria = _clasificar_puesto(boleta, puesto)
            if categoria == "dasuten":
                puestos_dasuten.append(puesto)
            elif categoria:
                puestos_por_categoria[categoria].append(puesto)
            else:
                puestos_sin_categoria.add(
                    f"{puesto['organo']} — {puesto['nombre']}".strip(" —")
                )

        columnas = [
            {
                **boleta,
                "categoria": categoria,
                "puestos": puestos_por_categoria[categoria],
            }
            if puestos_por_categoria[categoria]
            else None
            for categoria in CATEGORIAS_BOLETA
        ]
        if any(columnas):
            filas.append({"columnas": columnas})

        if columnas[2] is not None:
            filas.append({
                "columnas": [
                    None, None, columnas[2],
                    columnas[3] if _comparte_basicas_por_departamento(" ".join(boleta["claustros"])) else None,
                ],
                "fila_departamental": True,
            })

        if puestos_dasuten and boleta["clave_lista"] not in listas_dasuten_emitidas:
            listas_dasuten_emitidas.add(boleta["clave_lista"])
            filas.append({
                "columnas": [
                    {
                        **boleta,
                        "categoria": "dasuten",
                        "puestos": puestos_dasuten,
                    },
                    None,
                    None,
                    None,
                ],
                "fila_dasuten": True,
            })

    for fila in filas[1::FILAS_POR_PAGINA]:
        basicas = fila["columnas"][3]
        if basicas and "estudiante" in slugify(" ".join(basicas["claustros"])):
            fila["columnas"][3] = None

    return filas, sorted(puestos_sin_categoria)


def validar_boletas_pdf(eleccion) -> ValidacionBoletasPDF:
    filas, puestos_sin_categoria = _crear_filas_boletas(_obtener_boletas(eleccion))
    cantidad = sum(
        columna is not None
        for fila in filas
        for columna in fila["columnas"]
    )
    motivos = []
    if puestos_sin_categoria:
        motivos.append(
            "No se pudo ubicar en las cuatro columnas el/los puesto(s): "
            + ", ".join(puestos_sin_categoria)
            + "."
        )
    if cantidad == 0:
        motivos.append(
            "La elección no tiene listas activas con candidatos en puestos reconocidos para generar boletas."
        )
    if motivos:
        return ValidacionBoletasPDF(
            apto=False,
            cantidad_boletas=cantidad,
            motivos=motivos,
        )
    return ValidacionBoletasPDF(apto=True, cantidad_boletas=cantidad)


def generar_nombre_archivo_boletas(eleccion) -> str:
    fecha = timezone.now().strftime("%Y%m%d")
    slug = slugify(eleccion.nombre) or f"eleccion-{eleccion.id}"
    return f"boletas_{slug}_{fecha}.pdf"


def _construir_contenido_boleta(boleta, eleccion, ancho, escala):
    participacion = boleta["participacion"]
    estilos_base = getSampleStyleSheet()
    estilos = {
        "titulo": ParagraphStyle(
            "boleta_titulo",
            parent=estilos_base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8 * escala,
            leading=9 * escala,
            alignment=TA_CENTER,
        ),
        "eleccion": ParagraphStyle(
            "boleta_eleccion",
            parent=estilos_base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5 * escala,
            leading=7.5 * escala,
            alignment=TA_CENTER,
        ),
        "detalle": ParagraphStyle(
            "boleta_detalle",
            parent=estilos_base["Normal"],
            fontName="Helvetica",
            fontSize=6 * escala,
            leading=7 * escala,
            alignment=TA_CENTER,
        ),
        "lista": ParagraphStyle(
            "boleta_lista",
            parent=estilos_base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7 * escala,
            leading=8 * escala,
            alignment=TA_CENTER,
        ),
        "voto": ParagraphStyle(
            "boleta_voto",
            parent=estilos_base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5 * escala,
            leading=7.5 * escala,
        ),
        "puesto": ParagraphStyle(
            "boleta_puesto",
            parent=estilos_base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5 * escala,
            leading=7 * escala,
            spaceBefore=1 * mm * escala,
        ),
        "tipo": ParagraphStyle(
            "boleta_tipo",
            parent=estilos_base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=5.5 * escala,
            leading=6 * escala,
        ),
        "candidato": ParagraphStyle(
            "boleta_candidato",
            parent=estilos_base["Normal"],
            fontName="Helvetica",
            fontSize=6 * escala,
            leading=7 * escala,
        ),
    }
    elementos = [
        Paragraph(
            f"ELECCIONES CLAUSTRO {escape(', '.join(boleta['claustros']).upper())}",
            estilos["titulo"],
        ),
        Paragraph(escape(eleccion.nombre.upper()), estilos["eleccion"]),
    ]

    if boleta["departamento"] is not None:
        elementos.append(
            Paragraph(
                f"DEPARTAMENTO: {escape(str(boleta['departamento']).upper())}",
                estilos["detalle"],
            )
        )
    elementos.extend((
        Spacer(1, 1 * mm * escala),
        Paragraph(
            f"LISTA: {escape(participacion.nombre_lista or 'Sin nombre')}",
            estilos["lista"],
        ),
        NumeroListaBoleta(participacion.numero_lista, ancho, escala),
        Paragraph(
            f"DOY MI VOTO PARA: {ETIQUETAS_CATEGORIA[boleta['categoria']]}",
            estilos["voto"],
        ),
        Paragraph("CANDIDATOS:", estilos["tipo"]),
    ))

    for puesto in boleta["puestos"]:
        titulo = " — ".join(
            parte for parte in (puesto["organo"], puesto["nombre"]) if parte
        )
        elementos.append(Paragraph(escape(titulo.upper()), estilos["puesto"]))
        for tipo, etiqueta in (
            (Candidato.Tipo.TITULAR, "TITULARES"),
            (Candidato.Tipo.SUPLENTE, "SUPLENTES"),
        ):
            candidatos = [
                candidato
                for candidato in puesto["candidatos"]
                if candidato.tipo == tipo
            ]
            if not candidatos:
                continue
            elementos.append(Paragraph(etiqueta, estilos["tipo"]))
            elementos.extend(
                Paragraph(
                    f"{candidato.orden}. {escape((candidato.elector.nombre_completo if candidato.elector_id else candidato.nombre).strip())}",
                    estilos["candidato"],
                )
                for candidato in candidatos
            )
    return elementos


def _dibujar_boleta_cuadrante(canvas, boleta, eleccion, x, y, ancho, alto):
    relleno = 2 * mm
    ancho_contenido = ancho - 2 * relleno
    alto_contenido = alto - 2 * relleno
    contenido = None

    for escala in (1, 0.9, 0.8, 0.7, 0.6, 0.5):
        candidato = _construir_contenido_boleta(
            boleta,
            eleccion,
            ancho_contenido,
            escala,
        )
        altura_total = sum(
            elemento.wrap(ancho_contenido, alto_contenido)[1]
            for elemento in candidato
        )
        if altura_total <= alto_contenido:
            contenido = candidato
            break
    if contenido is None:
        raise ValueError(
            f"La boleta {boleta['participacion'].numero_lista} supera el espacio "
            "disponible en su cuadrante."
        )

    canvas.saveState()
    cursor_y = y + alto - relleno
    for elemento in contenido:
        _, altura_elemento = elemento.wrap(ancho_contenido, alto_contenido)
        cursor_y -= altura_elemento
        elemento.drawOn(canvas, x + relleno, cursor_y)
    canvas.restoreState()


def _dibujar_marca_agua_octante(canvas, x, y, ancho, alto):
    canvas.saveState()
    canvas.translate(x + ancho / 2, y + alto / 2)
    canvas.rotate(35)
    canvas.setFillColor(colors.HexColor("#dddddd"))
    canvas.setFont("Helvetica-Bold", 22)
    canvas.drawCentredString(0, 13, "Demo Proyecto Final")
    canvas.drawCentredString(0, -13, "VOTO UTN")
    canvas.restoreState()


class CuadriculaBoletas(Flowable):
    def __init__(self, filas, eleccion, ancho, alto):
        super().__init__()
        self.filas = filas
        self.eleccion = eleccion
        self.width = ancho
        self.height = alto

    def draw(self):
        ancho_cuadrante = self.width / ANCHO_CUADRANTES
        alto_fila = self.height / FILAS_POR_PAGINA
        self.canv.saveState()
        self.canv.setLineWidth(0.7)
        for indice_fila in range(FILAS_POR_PAGINA):
            y = self.height - (indice_fila + 1) * alto_fila
            for indice_columna in range(ANCHO_CUADRANTES):
                x = indice_columna * ancho_cuadrante
                _dibujar_marca_agua_octante(
                    self.canv,
                    x,
                    y,
                    ancho_cuadrante,
                    alto_fila,
                )
        for indice_fila in range(FILAS_POR_PAGINA):
            fila = (
                self.filas[indice_fila]
                if indice_fila < len(self.filas)
                else {"columnas": [None] * ANCHO_CUADRANTES}
            )
            y = self.height - (indice_fila + 1) * alto_fila
            for indice_columna, boleta in enumerate(fila["columnas"]):
                x = indice_columna * ancho_cuadrante
                self.canv.rect(x, y, ancho_cuadrante, alto_fila)
                if boleta is not None:
                    _dibujar_boleta_cuadrante(
                        self.canv,
                        boleta,
                        self.eleccion,
                        x,
                        y,
                        ancho_cuadrante,
                        alto_fila,
                    )
        self.canv.restoreState()


def generar_boletas_pdf(eleccion) -> bytes:
    filas, puestos_sin_categoria = _crear_filas_boletas(_obtener_boletas(eleccion))
    if puestos_sin_categoria:
        raise ValueError(
            "No se pudo ubicar en las cuatro columnas el/los puesto(s): "
            + ", ".join(puestos_sin_categoria)
            + "."
        )
    if not filas:
        raise ValueError(
            "La elección no tiene puestos reconocidos con candidatos para generar boletas."
        )

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=PAGINA,
        rightMargin=MARGEN,
        leftMargin=MARGEN,
        topMargin=MARGEN,
        bottomMargin=MARGEN,
        title=f"Boletas electorales - {eleccion.nombre}",
        author="Junta Electoral UTN",
    )
    ancho = PAGINA[0] - 2 * MARGEN - 2 * RELLENO_MARCO_PDF_PT
    alto = PAGINA[1] - 2 * MARGEN - 2 * RELLENO_MARCO_PDF_PT
    elementos = []
    for indice in range(0, len(filas), FILAS_POR_PAGINA):
        if indice:
            elementos.append(PageBreak())
        elementos.append(
            CuadriculaBoletas(
                filas[indice:indice + FILAS_POR_PAGINA],
                eleccion,
                ancho,
                alto,
            )
        )

    documento.build(elementos)
    return buffer.getvalue()
