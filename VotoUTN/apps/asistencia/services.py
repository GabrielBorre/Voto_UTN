from dataclasses import dataclass
from django.db import IntegrityError, transaction
from apps.elecciones.models import Eleccion
from apps.elecciones.models import Votante
from .models import Asistencia


@dataclass(frozen=True)
class ResultadoAsistencia:
    created: list[str]
    already_registered: list[str]
    invalid: list[str]


class ServicioAsistencia:
    """Caso de uso: registra códigos de una hoja de padrón de forma atómica."""
    @staticmethod
    def registrar_lote(*, eleccion: Eleccion, voter_codes: list[str], user) -> ResultadoAsistencia:
        cleaned = list(dict.fromkeys(
            code.strip().removeprefix("VOTER:").strip()
            for code in voter_codes if code and code.strip()
        ))
        valid_codes = set(Votante.objects.filter(legajo__in=cleaned).values_list("legajo", flat=True))
        invalid = sorted(set(cleaned) - valid_codes)
        existing = set(Asistencia.objects.filter(eleccion=eleccion, voter_code__in=valid_codes).values_list("voter_code", flat=True))
        new_codes = [code for code in cleaned if code in valid_codes and code not in existing]
        with transaction.atomic():
            Asistencia.objects.bulk_create([
                Asistencia(eleccion=eleccion, voter_code=code, scanned_by=user) for code in new_codes
            ], ignore_conflicts=True)
        registered = set(Asistencia.objects.filter(eleccion=eleccion, voter_code__in=new_codes).values_list("voter_code", flat=True))
        return ResultadoAsistencia(created=sorted(registered - existing), already_registered=sorted(existing), invalid=invalid)
