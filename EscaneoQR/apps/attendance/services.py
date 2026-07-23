from dataclasses import dataclass
from django.db import IntegrityError, transaction
from apps.elections.models import Election
from apps.elections.models import Voter
from .models import Attendance


@dataclass(frozen=True)
class AttendanceResult:
    created: list[str]
    already_registered: list[str]
    invalid: list[str]


class AttendanceService:
    """Caso de uso: registra códigos de una hoja de padrón de forma atómica."""
    @staticmethod
    def register_batch(*, election: Election, voter_codes: list[str], user) -> AttendanceResult:
        cleaned = list(dict.fromkeys(
            code.strip().removeprefix("VOTER:").strip()
            for code in voter_codes if code and code.strip()
        ))
        valid_codes = set(Voter.objects.filter(legajo__in=cleaned).values_list("legajo", flat=True))
        invalid = sorted(set(cleaned) - valid_codes)
        existing = set(Attendance.objects.filter(election=election, voter_code__in=valid_codes).values_list("voter_code", flat=True))
        new_codes = [code for code in cleaned if code in valid_codes and code not in existing]
        with transaction.atomic():
            Attendance.objects.bulk_create([
                Attendance(election=election, voter_code=code, scanned_by=user) for code in new_codes
            ], ignore_conflicts=True)
        registered = set(Attendance.objects.filter(election=election, voter_code__in=new_codes).values_list("voter_code", flat=True))
        return AttendanceResult(created=sorted(registered - existing), already_registered=sorted(existing), invalid=invalid)
