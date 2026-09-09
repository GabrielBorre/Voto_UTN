from django.conf import settings
from django.db import models


class EventoAuditoria(models.Model):
    accion = models.CharField(max_length=120)
    entidad = models.CharField(max_length=120)
    entidad_id = models.CharField(max_length=80, blank=True)
    eleccion = models.ForeignKey(
        "elecciones.Eleccion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
    )
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    agente_usuario = models.CharField(max_length=300, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-creado_en", "-id")
        indexes = [
            models.Index(fields=("accion", "creado_en"), name="auditoria_accion_fecha_idx"),
            models.Index(fields=("entidad", "entidad_id"), name="auditoria_entidad_idx"),
        ]

    def __str__(self):
        return f"{self.accion} {self.entidad} {self.entidad_id}".strip()
