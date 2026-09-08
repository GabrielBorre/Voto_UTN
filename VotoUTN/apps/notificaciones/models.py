from django.db import models

from apps.elecciones.models import Eleccion
from apps.parametros.models import Claustro


class PlantillaNotificacion(models.Model):
    nombre = models.CharField(max_length=160, unique=True)
    asunto = models.CharField(max_length=180)
    contenido = models.TextField()
    roles_destinatarios = models.JSONField(default=list)
    claustros = models.ManyToManyField(
        Claustro,
        related_name="plantillas_notificacion",
        blank=True,
        db_table="elecciones_plantillanotificacion_claustros",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_plantillanotificacion"
        ordering = ("nombre",)


class EnvioNotificacion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Enviado"
        ERROR = "error", "Error"

    plantilla = models.ForeignKey(PlantillaNotificacion, on_delete=models.PROTECT, related_name="envios")
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="envios_notificacion", null=True, blank=True)
    destinatario = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="notificaciones")
    asunto = models.CharField(max_length=180)
    contenido = models.TextField()
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    creada_en = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)
    leida_en = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "elecciones_envionotificacion"
        ordering = ("-creada_en",)
