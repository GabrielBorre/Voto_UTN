from django.conf import settings
from django.db import models
from apps.elecciones.models import Mesa, RegistroPadron


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
