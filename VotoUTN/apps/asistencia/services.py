import base64
import struct
import hmac
import hashlib
from dataclasses import dataclass
from django.conf import settings
from django.db import transaction
from apps.elecciones.models import Eleccion, Elector
from apps.usuarios.permisos import puede_registrar_participacion
from .models import Asistencia


@dataclass(frozen=True)
class ResultadoAsistencia:
    creados: list[str]
    ya_registrados: list[str]
    invalidos: list[str]


class ServicioAsistencia:
    """Caso de uso: registra códigos de una hoja de padrón de forma atómica."""

    @staticmethod
    def _parse_signed_code(raw_code) -> tuple[int, int, str] | None:
        """
        Parsea y valida un código QR en formato Base64 URL-safe de 16 caracteres.
        Contiene 12 bytes empaquetados (8 bytes de datos + 4 bytes de firma HMAC).
        """
        if not isinstance(raw_code, str):
            return None

        code_clean = raw_code.strip()

        # Recomponer padding de Base64 si no viene presente (para que la longitud sea múltiplo de 4)
        padded_code = code_clean + "=" * (-len(code_clean) % 4)

        try:
            qr_bytes = base64.urlsafe_b64decode(padded_code)
        except Exception:
            return None

        # 1. Validar que la decodificación de exactamente 12 bytes
        if len(qr_bytes) != 12:
            return None

        # 2. Separar datos (8 bytes) y firma recibida (4 bytes)
        data_bytes = qr_bytes[:8]
        signature = qr_bytes[8:]

        # 3. Recalcular la firma HMAC esperada
        expected_signature = hmac.new(
            settings.CLAVE_FIRMA_QR.encode("utf-8"),
            data_bytes,
            hashlib.sha256,
        ).digest()[:4]

        # 4. Validar firma en tiempo constante
        if not hmac.compare_digest(signature, expected_signature):
            return None

        # 5. Desempaquetar datos: Elección (Short), Mesa (Short), Legajo (Unsigned Int)
        election_id, mesa_numero, legajo_int = struct.unpack(">HHI", data_bytes)

        return election_id, mesa_numero, str(legajo_int)

    @staticmethod
    def registrar_lote(*, eleccion: Eleccion, codigos_qr: list, usuario) -> ResultadoAsistencia:
        # Eliminamos duplicados manteniendo limpieza de strings
        incoming = list(dict.fromkeys(
            codigo.strip() for codigo in codigos_qr if isinstance(codigo, str) and codigo.strip()
        ))
        
        parsed_codes = []
        invalidos = []

        for raw_code in incoming:
            parsed = ServicioAsistencia._parse_signed_code(raw_code)
            if parsed is None:
                invalidos.append(raw_code)
                continue

            eleccion_id, mesa_numero, codigo_elector = parsed
            if eleccion_id != eleccion.id:
                invalidos.append(raw_code)
                continue

            parsed_codes.append((raw_code, mesa_numero, codigo_elector))

        codigos_elector = list(dict.fromkeys(codigo for _, _, codigo in parsed_codes))
        electores = {
            elector.legajo: elector
            for elector in Elector.objects.select_related("mesa").filter(legajo__in=codigos_elector)
        }

        codigos_validos = []
        for raw_code, mesa_numero, codigo_elector in parsed_codes:
            elector = electores.get(codigo_elector)
            if elector is None or elector.mesa is None:
                invalidos.append(raw_code)
                continue
            if elector.mesa.eleccion_id != eleccion.id or elector.mesa.numero != mesa_numero:
                invalidos.append(raw_code)
                continue
            if not puede_registrar_participacion(usuario, eleccion, elector.mesa):
                invalidos.append(raw_code)
                continue
            codigos_validos.append(codigo_elector)

        codigos_limpios = list(dict.fromkeys(codigos_validos))
        existentes = set(
            Asistencia.objects.filter(eleccion=eleccion, codigo_elector__in=codigos_limpios).values_list("codigo_elector", flat=True)
        )
        codigos_nuevos = [codigo for codigo in codigos_limpios if codigo not in existentes]
        
        with transaction.atomic():
            Asistencia.objects.bulk_create([
                Asistencia(eleccion=eleccion, codigo_elector=codigo, registrada_por=usuario) for codigo in codigos_nuevos
            ], ignore_conflicts=True)
            
            registrados = set(
                Asistencia.objects.filter(eleccion=eleccion, codigo_elector__in=codigos_nuevos).values_list("codigo_elector", flat=True)
            )
            
        return ResultadoAsistencia(
            creados=sorted(registrados - existentes),
            ya_registrados=sorted(existentes),
            invalidos=sorted(set(str(invalido) for invalido in invalidos)),
        )

    @staticmethod
    def registrar_manual(*, eleccion: Eleccion, mesa_numero: int, legajo: str, usuario) -> ResultadoAsistencia:
        legajo_clean = str(legajo).strip()

        elector = (
            Elector.objects.select_related("mesa")
            .filter(legajo=legajo_clean)
            .first()
        )

        if (
            elector is None
            or elector.mesa is None
            or elector.mesa.eleccion_id != eleccion.id
            or elector.mesa.numero != mesa_numero
        ):
            return ResultadoAsistencia(
                creados=[],
                ya_registrados=[],
                invalidos=[f"Mesa {mesa_numero} / Legajo {legajo_clean}"],
            )

        if not puede_registrar_participacion(usuario, eleccion, elector.mesa):
            return ResultadoAsistencia(creados=[], ya_registrados=[], invalidos=[f"Mesa {mesa_numero} / Sin permiso"])

        existentes = set(
            Asistencia.objects.filter(eleccion=eleccion, codigo_elector=legajo_clean).values_list("codigo_elector", flat=True)
        )

        if legajo_clean in existentes:
            return ResultadoAsistencia(creados=[], ya_registrados=[legajo_clean], invalidos=[])

        with transaction.atomic():
            Asistencia.objects.create(eleccion=eleccion, codigo_elector=legajo_clean, registrada_por=usuario)

        return ResultadoAsistencia(creados=[legajo_clean], ya_registrados=[], invalidos=[])
