from django.core.exceptions import ValidationError
from django.db import models

from apps.padron.models import RegistroPadron


class TipoJustificativo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_tipojustificativo"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class JustificativoAusencia(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADO = "aprobado", "Aprobado"
        RECHAZADO = "rechazado", "Rechazado"

    registro_padron = models.ForeignKey(RegistroPadron, on_delete=models.PROTECT, related_name="justificativos")
    tipo = models.ForeignKey(TipoJustificativo, on_delete=models.PROTECT, related_name="justificativos")
    detalle = models.TextField()
    documento = models.FileField(upload_to="justificativos/%Y/%m/%d", blank=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    presentada_en = models.DateTimeField(auto_now_add=True)
    resuelta_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True, related_name="justificativos_resueltos")
    resuelta_en = models.DateTimeField(null=True, blank=True)
    observacion_resolucion = models.TextField(blank=True)

    class Meta:
        db_table = "elecciones_justificativoausencia"

    def clean(self):
        if self.resuelta_por_id and self.estado == self.Estado.PENDIENTE:
            raise ValidationError({"estado": "Un justificativo resuelto debe estar aprobado o rechazado."})
