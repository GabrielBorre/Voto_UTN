from django.conf import settings
from django.db import models
from apps.elecciones.models import Eleccion, Mesa, RegistroPadron


class RegistroParticipacion(models.Model):
    class Metodo(models.TextChoices):
        QR = "qr", "QR"
        MANUAL = "manual", "Manual"

    registro_padron = models.ForeignKey(RegistroPadron, on_delete=models.PROTECT, related_name="participaciones")
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="participaciones")
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrada_en = models.DateTimeField(auto_now_add=True)
    metodo = models.CharField(max_length=10, choices=Metodo.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("registro_padron",), name="participacion_unica_por_padron")]


class Asistencia(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="asistencias")
    codigo_elector = models.CharField(max_length=180)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "codigo_elector"), name="asistencia_unica_por_eleccion")]
        indexes = [models.Index(fields=("eleccion", "codigo_elector"), name="asistencia_eleccion_codigo_idx")]

    def __str__(self):
        return f"{self.eleccion}: {self.codigo_elector}"
