from django.core.exceptions import ValidationError
from django.db import models

from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.parametros.models import Sede, Turno


class CandidaturaAutoridad(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="candidatura_autoridad")
    cargada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="candidaturas_autoridad_cargadas")
    cargada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "elecciones_candidaturaautoridad"


class AsignacionAutoridad(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADA = "confirmada", "Confirmada"
        RECHAZADA = "rechazada", "Rechazada"

    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="asignacion_autoridad")
    candidatura = models.OneToOneField(CandidaturaAutoridad, on_delete=models.PROTECT, related_name="asignacion", null=True, blank=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="autoridades")
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    asignada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="autoridades_asignadas")
    asignada_en = models.DateTimeField(auto_now_add=True)
    respondida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "elecciones_asignacionautoridad"

    def clean(self):
        if self.registro_padron_id and self.mesa_id:
            if self.candidatura_id and self.candidatura.registro_padron_id != self.registro_padron_id:
                raise ValidationError({"candidatura": "Debe corresponder al mismo elector del padron."})
            if self.registro_padron.eleccion_id != self.mesa.eleccion_id:
                raise ValidationError({"mesa": "Debe pertenecer a la misma eleccion que el padron."})
            if self.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id != self.mesa.eleccion_claustro_departamento.eleccion_claustro_id:
                raise ValidationError({"mesa": "La autoridad debe pertenecer al mismo claustro que la mesa."})


class PreferenciaAutoridad(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="preferencia_autoridad")
    sede_preferida = models.ForeignKey(Sede, on_delete=models.PROTECT, null=True, blank=True, related_name="preferencias_autoridad")
    turno_preferido = models.ForeignKey(Turno, on_delete=models.PROTECT, null=True, blank=True, related_name="preferencias_autoridad")
    disponible = models.BooleanField(default=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "elecciones_preferenciaautoridad"

    def clean(self):
        if self.registro_padron_id and self.sede_preferida_id and self.sede_preferida_id != self.registro_padron.sede_id:
            raise ValidationError({"sede_preferida": "La sede preferida debe ser la sede del padron."})
