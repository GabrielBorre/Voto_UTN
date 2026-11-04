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

    class Ausencia(models.TextChoices):
        VOTAR = "votar", "Ausencia a votar"
        AUTORIDAD = "autoridad", "Ausencia como autoridad de mesa"

    class ValidacionComprobante(models.TextChoices):
        NO_APLICA = "no_aplica", "No aplica"
        PENDIENTE = "pendiente", "Sin validar"
        VALIDO = "valido", "QR válido para el elector"
        INVALIDO = "invalido", "QR no válido para el elector"
        NO_DETECTADO = "no_detectado", "No se detectó un QR"
        NO_PROCESABLE = "no_procesable", "Requiere revisión manual"
        SIN_COMPROBANTE = "sin_comprobante", "Comprobante extraviado"

    registro_padron = models.ForeignKey(RegistroPadron, on_delete=models.PROTECT, related_name="justificativos")
    ausencia = models.CharField(max_length=16, choices=Ausencia.choices, default=Ausencia.VOTAR)
    tipo = models.ForeignKey(
        TipoJustificativo, on_delete=models.PROTECT, related_name="justificativos", null=True, blank=True,
    )
    reclamo_participacion = models.BooleanField("Voté, pero aparezco como ausente", default=False)
    detalle = models.TextField()
    documento = models.FileField(upload_to="justificativos/%Y/%m/%d", blank=True)
    comprobante_extraviado = models.BooleanField(
        "Perdí el comprobante de votación", default=False,
    )
    validacion_comprobante = models.CharField(
        "Validación del comprobante", max_length=16,
        choices=ValidacionComprobante.choices, default=ValidacionComprobante.NO_APLICA,
    )
    detalle_validacion_comprobante = models.TextField("Detalle de la validación", blank=True)
    comprobante_validado_en = models.DateTimeField(null=True, blank=True)
    # Copia del RegistroParticipacion eliminado al aprobar el reclamo, para auditoría y restauración.
    respaldo_participacion = models.JSONField(default=dict, blank=True)
    participacion_anulada_en = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    presentada_en = models.DateTimeField(auto_now_add=True)
    resuelta_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True, related_name="justificativos_resueltos")
    resuelta_en = models.DateTimeField(null=True, blank=True)
    observacion_resolucion = models.TextField(blank=True)

    class Meta:
        db_table = "elecciones_justificativoausencia"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(reclamo_participacion=True, ausencia="votar", tipo__isnull=True)
                    | models.Q(reclamo_participacion=False, tipo__isnull=False)
                ),
                name="justificativo_tipo_o_reclamo_participacion",
            ),
        ]

    @property
    def motivo(self):
        if self.reclamo_participacion:
            return self._meta.get_field("reclamo_participacion").verbose_name
        return str(self.tipo) if self.tipo_id else ""

    def clean(self):
        if self.resuelta_por_id and self.estado == self.Estado.PENDIENTE:
            raise ValidationError({"estado": "Un justificativo resuelto debe estar aprobado o rechazado."})
