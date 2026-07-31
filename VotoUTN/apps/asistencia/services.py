import base64
import struct
import hmac
import hashlib
from dataclasses import dataclass
from django.conf import settings
from django.db import transaction
from apps.elecciones.models import Eleccion, Votante
from .models import Asistencia


@dataclass(frozen=True)
class ResultadoAsistencia:
    created: list[str]
    already_registered: list[str]
    invalid: list[str]


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
            settings.SECRET_KEY.encode("utf-8"),
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
    def registrar_lote(*, eleccion: Eleccion, voter_codes: list, user) -> ResultadoAsistencia:
        # Eliminamos duplicados manteniendo limpieza de strings
        incoming = list(dict.fromkeys(
            code.strip() for code in voter_codes if isinstance(code, str) and code.strip()
        ))
        
        parsed_codes = []
        invalid = []

        for raw_code in incoming:
            parsed = ServicioAsistencia._parse_signed_code(raw_code)
            if parsed is None:
                invalid.append(raw_code)
                continue

            election_id, mesa_numero, voter_code = parsed
            if election_id != eleccion.id:
                invalid.append(raw_code)
                continue

            parsed_codes.append((raw_code, mesa_numero, voter_code))

        candidate_codes = list(dict.fromkeys(voter_code for _, _, voter_code in parsed_codes))
        voters = {
            voter.legajo: voter
            for voter in Votante.objects.select_related("mesa").filter(legajo__in=candidate_codes)
        }

        valid_cleaned = []
        for raw_code, mesa_numero, voter_code in parsed_codes:
            voter = voters.get(voter_code)
            if voter is None or voter.mesa is None:
                invalid.append(raw_code)
                continue
            if voter.mesa.eleccion_id != eleccion.id or voter.mesa.numero != mesa_numero:
                invalid.append(raw_code)
                continue
            valid_cleaned.append(voter_code)

        cleaned = list(dict.fromkeys(valid_cleaned))
        existing = set(
            Asistencia.objects.filter(eleccion=eleccion, voter_code__in=cleaned).values_list("voter_code", flat=True)
        )
        new_codes = [code for code in cleaned if code not in existing]
        
        with transaction.atomic():
            Asistencia.objects.bulk_create([
                Asistencia(eleccion=eleccion, voter_code=code, scanned_by=user) for code in new_codes
            ], ignore_conflicts=True)
            
            registered = set(
                Asistencia.objects.filter(eleccion=eleccion, voter_code__in=new_codes).values_list("voter_code", flat=True)
            )
            
        return ResultadoAsistencia(
            created=sorted(registered - existing),
            already_registered=sorted(existing),
            invalid=sorted(set(str(inv) for inv in invalid)),
        )

    @staticmethod
    def registrar_manual(*, eleccion: Eleccion, mesa_numero: int, legajo: str, user) -> ResultadoAsistencia:
        legajo_clean = str(legajo).strip()

        voter = (
            Votante.objects.select_related("mesa")
            .filter(legajo=legajo_clean)
            .first()
        )

        if (
            voter is None
            or voter.mesa is None
            or voter.mesa.eleccion_id != eleccion.id
            or voter.mesa.numero != mesa_numero
        ):
            return ResultadoAsistencia(
                created=[],
                already_registered=[],
                invalid=[f"Mesa {mesa_numero} / Legajo {legajo_clean}"],
            )

        existing = set(
            Asistencia.objects.filter(eleccion=eleccion, voter_code=legajo_clean).values_list("voter_code", flat=True)
        )

        if legajo_clean in existing:
            return ResultadoAsistencia(created=[], already_registered=[legajo_clean], invalid=[])

        with transaction.atomic():
            Asistencia.objects.create(eleccion=eleccion, voter_code=legajo_clean, scanned_by=user)

        return ResultadoAsistencia(created=[legajo_clean], already_registered=[], invalid=[])