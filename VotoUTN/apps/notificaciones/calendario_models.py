from django.db import models


class MensajeProgramado(models.Model):
    eleccion = models.ForeignKey("elecciones.Eleccion", on_delete=models.PROTECT, related_name="mensajes_programados")
    fecha_administrativa = models.ForeignKey("parametros.FechaAdministrativa", on_delete=models.PROTECT)
    estado_eleccion = models.CharField(max_length=16)
    plantilla = models.ForeignKey("notificaciones.PlantillaNotificacion", on_delete=models.PROTECT)
    programado_para = models.DateTimeField()
    recordatorio = models.BooleanField(default=False)
    habilitado = models.BooleanField(default=True)
    procesado_en = models.DateTimeField(null=True, blank=True, editable=False)
    error = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ("programado_para", "pk")
        indexes = [models.Index(fields=("habilitado", "procesado_en", "programado_para"), name="mensaje_calendario_pendiente")]
