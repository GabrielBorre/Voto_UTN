from django.conf import settings
from django.db import models
from apps.elecciones.models import Eleccion


class Asistencia(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="attendances")
    voter_code = models.CharField(max_length=180)
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "voter_code"), name="unique_attendance_per_election")]
        indexes = [models.Index(fields=("eleccion", "voter_code"))]

    def __str__(self):
        return f"{self.eleccion}: {self.voter_code}"
