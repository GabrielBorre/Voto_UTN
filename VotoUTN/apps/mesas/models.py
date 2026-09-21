from django.core.exceptions import ValidationError
from django.db import models

from apps.elecciones.models import Eleccion, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, EleccionTurno
from apps.padron.models import RegistroPadron
from apps.parametros.models import Sede, Turno


class Mesa(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="mesas")
    numero = models.PositiveIntegerField("numero")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    generada_automaticamente = models.BooleanField(default=False)

    class Meta:
        db_table = "elecciones_mesa"
        ordering = ["eleccion_id", "numero"]
        constraints = [models.UniqueConstraint(fields=("eleccion", "numero"), name="unique_mesa_per_eleccion")]

    def clean(self):
        if self.eleccion_claustro_departamento_id and self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma eleccion."})
        if self.eleccion_claustro_departamento_id and self.sede_id and not EleccionClaustroDepartamentoSede.objects.filter(eleccion_claustro_departamento=self.eleccion_claustro_departamento, sede=self.sede).exists():
            raise ValidationError({"sede": "La sede debe estar habilitada para el departamento."})
        if self.eleccion_id and self.turno_id and not EleccionTurno.objects.filter(eleccion_id=self.eleccion_id, turno_id=self.turno_id).exists():
            raise ValidationError({"turno": "El turno debe estar habilitado para la eleccion."})

    def __str__(self):
        return f"{self.eleccion} - Mesa {self.numero}"

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = Mesa.objects.filter(pk=self.pk).first()
            tiene_qr_emitidos = self.asignaciones_padron.filter(
                registro_padron__qr_generado_en__isnull=False
            ).exists()
            if anterior and tiene_qr_emitidos and any(
                getattr(anterior, campo) != getattr(self, campo)
                for campo in ("eleccion_id", "numero", "eleccion_claustro_departamento_id", "sede_id", "turno_id")
            ):
                raise ValidationError("No se puede modificar una mesa con códigos QR emitidos.")
        super().save(*args, **kwargs)


class AsignacionMesa(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="asignacion_mesa")
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="asignaciones_padron")

    class Meta:
        db_table = "elecciones_asignacionmesa"

    def clean(self):
        if self.registro_padron_id and self.mesa_id and self.registro_padron.eleccion_id != self.mesa.eleccion_id:
            raise ValidationError({"mesa": "Debe pertenecer a la misma eleccion del padron."})
        if (
            self.registro_padron_id
            and self.mesa_id
            and self.registro_padron.qr_generado_en
            and self.registro_padron.numero_mesa_qr != self.mesa.numero
        ):
            raise ValidationError({"mesa": "El QR ya fue emitido para otra mesa."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.registro_padron.qr_generado_en:
            raise ValidationError("No se puede eliminar una asignación con el QR emitido.")
        return super().delete(*args, **kwargs)
