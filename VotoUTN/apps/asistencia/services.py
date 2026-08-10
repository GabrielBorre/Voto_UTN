import hashlib
import hmac
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.elecciones.models import Eleccion, RegistroPadron
from apps.usuarios.permisos import puede_registrar_participacion
from .models import RegistroParticipacion


@dataclass(frozen=True)
class ResultadoParticipacion:
    creados: list[str]
    ya_registrados: list[str]
    invalidos: list[str]
    invalidos_otra_eleccion: list[str]
    mesa_numero: int | None = None
    departamento_codigo: str | None = None


class ServicioRegistroParticipacion:
    VERSION_QR = "v1"
    LONGITUD_IDENTIFICADOR = 8
    LONGITUD_FIRMA = 4
    ANCHO_BASE36_ELECCION = 2
    ANCHO_BASE36_MESA = 2
    ALFABETO_QR = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    @classmethod
    def _to_base36(cls, valor: int, ancho: int):
        if valor < 0:
            raise ValueError("El valor no puede ser negativo.")
        caracteres = []
        while valor:
            valor, resto = divmod(valor, 36)
            caracteres.append(cls.ALFABETO_QR[resto])
        texto = "".join(reversed(caracteres or ["0"]))
        return texto.rjust(ancho, "0")

    @classmethod
    def _from_base36(cls, texto: str):
        return int(texto, 36)

    @classmethod
    def _firma_corta(cls, cuerpo: str):
        digest = hmac.new(
            settings.CLAVE_FIRMA_QR.encode("utf-8"),
            cuerpo.encode("ascii"),
            hashlib.sha256,
        ).digest()
        valor = int.from_bytes(digest[:2], "big")
        return cls._to_base36(valor, cls.LONGITUD_FIRMA)

    @classmethod
    def generar_codigo_qr(cls, *, eleccion_id, mesa_numero, identificador_qr):
        identificador = str(identificador_qr).strip().upper()
        if not identificador or len(identificador) != cls.LONGITUD_IDENTIFICADOR or not identificador.isalnum():
            raise ValueError("El identificador QR debe ser alfanumerico y de longitud 8.")
        cuerpo = (
            cls._to_base36(int(eleccion_id), cls.ANCHO_BASE36_ELECCION)
            + cls._to_base36(int(mesa_numero), cls.ANCHO_BASE36_MESA)
            + identificador
        )
        firma = cls._firma_corta(cuerpo)
        return f"{cls.VERSION_QR.upper()}.{cuerpo}{firma}"

    @classmethod
    def parsear_codigo_qr(cls, codigo):
        if not isinstance(codigo, str):
            return None
        version, separador, contenido = codigo.strip().upper().partition(".")
        if separador != "." or version != cls.VERSION_QR.upper():
            return None

        longitud_esperada = (
            cls.ANCHO_BASE36_ELECCION
            + cls.ANCHO_BASE36_MESA
            + cls.LONGITUD_IDENTIFICADOR
            + cls.LONGITUD_FIRMA
        )
        if len(contenido) != longitud_esperada or not contenido.isalnum():
            return None

        cuerpo = contenido[:-cls.LONGITUD_FIRMA]
        firma = contenido[-cls.LONGITUD_FIRMA:]
        esperada = cls._firma_corta(cuerpo)
        if not hmac.compare_digest(firma, esperada):
            return None

        eleccion_token = cuerpo[:cls.ANCHO_BASE36_ELECCION]
        mesa_token = cuerpo[
            cls.ANCHO_BASE36_ELECCION: cls.ANCHO_BASE36_ELECCION + cls.ANCHO_BASE36_MESA
        ]
        identificador = cuerpo[cls.ANCHO_BASE36_ELECCION + cls.ANCHO_BASE36_MESA:]
        try:
            eleccion_id = cls._from_base36(eleccion_token)
            mesa_numero = cls._from_base36(mesa_token)
        except ValueError:
            return None
        return eleccion_id, mesa_numero, identificador

    @classmethod
    def registrar_lote(cls, *, eleccion: Eleccion, codigos_qr: list, usuario) -> ResultadoParticipacion:
        codigos = list(dict.fromkeys(codigo.strip() for codigo in codigos_qr if isinstance(codigo, str) and codigo.strip()))
        parseados, invalidos, invalidos_otra_eleccion = [], [], []
        for codigo in codigos:
            parseado = cls.parsear_codigo_qr(codigo)
            if parseado is None:
                invalidos.append(codigo)
            elif parseado[0] != eleccion.id:
                invalidos.append(codigo)
                invalidos_otra_eleccion.append(codigo)
            else:
                parseados.append((codigo, parseado[1], parseado[2]))

        identificadores = [identificador for _, _, identificador in parseados]
        padrones = {
            padron.identificador_qr: padron
            for padron in RegistroPadron.objects.select_related(
                "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento"
            ).filter(
                eleccion=eleccion,
                activo=True,
                identificador_qr__in=identificadores,
            )
        }
        validos = []
        for codigo, mesa_numero, identificador in parseados:
            padron = padrones.get(identificador)
            mesa = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
            if padron is None or mesa is None or mesa.numero != mesa_numero or not puede_registrar_participacion(usuario, eleccion, mesa):
                invalidos.append(codigo)
            else:
                validos.append((identificador, padron, mesa))

        existentes = set(RegistroParticipacion.objects.filter(registro_padron__identificador_qr__in=[item[1].identificador_qr for item in validos]).values_list("registro_padron__identificador_qr", flat=True))
        nuevos = [item for item in validos if item[1].identificador_qr not in existentes]
        with transaction.atomic():
            RegistroParticipacion.objects.bulk_create([
                RegistroParticipacion(registro_padron=padron, mesa=mesa, registrada_por=usuario, metodo=RegistroParticipacion.Metodo.QR)
                for _, padron, mesa in nuevos
            ], ignore_conflicts=True)

        mesa_info = validos[0][2] if validos else None
        departamento_codigo = None
        if mesa_info and mesa_info.eleccion_claustro_departamento_id:
            departamento = mesa_info.eleccion_claustro_departamento.departamento
            departamento_codigo = departamento.codigo if departamento else None

        return ResultadoParticipacion(
            creados=[identificador for identificador, _, _ in nuevos],
            ya_registrados=[str(identificador) for identificador in existentes],
            invalidos=invalidos,
            invalidos_otra_eleccion=invalidos_otra_eleccion,
            mesa_numero=mesa_info.numero if mesa_info else None,
            departamento_codigo=departamento_codigo,
        )

    @classmethod
    def registrar_manual(cls, *, eleccion: Eleccion, mesa_numero: int, dni: str, usuario) -> ResultadoParticipacion:
        padron = RegistroPadron.objects.select_related(
            "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento"
        ).filter(eleccion=eleccion, activo=True, elector__dni=str(dni).strip()).first()
        mesa = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
        if padron is None or mesa is None or mesa.numero != mesa_numero or not puede_registrar_participacion(usuario, eleccion, mesa):
            return ResultadoParticipacion([], [], ["Elector no disponible para la mesa indicada."], [])
        if RegistroParticipacion.objects.filter(registro_padron=padron).exists():
            return ResultadoParticipacion(
                [],
                [padron.identificador_qr],
                [],
                [],
                mesa_numero=mesa.numero,
                departamento_codigo=mesa.eleccion_claustro_departamento.departamento.codigo if mesa.eleccion_claustro_departamento_id else None,
            )
        RegistroParticipacion.objects.create(registro_padron=padron, mesa=mesa, registrada_por=usuario, metodo=RegistroParticipacion.Metodo.MANUAL)
        return ResultadoParticipacion(
            [padron.identificador_qr],
            [],
            [],
            [],
            mesa_numero=mesa.numero,
            departamento_codigo=mesa.eleccion_claustro_departamento.departamento.codigo if mesa.eleccion_claustro_departamento_id else None,
        )
