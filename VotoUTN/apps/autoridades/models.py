from django.core.exceptions import ValidationError
from django.db import models

from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.parametros.models import Sede, Turno


class CandidaturaAutoridad(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="candidatura_autoridad")
    cargada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="candidaturas_autoridad_cargadas")
    cargada_en = models.DateTimeField(auto_now_add=True)
    excluida = models.BooleanField(default=False)

    class Meta:
        db_table = "elecciones_candidaturaautoridad"

    def __str__(self):
        elector = self.registro_padron.elector
        return f"{elector.nombre_completo} · DNI {elector.dni} · Legajo {elector.legajo}"


class AsignacionAutoridad(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADA = "confirmada", "Confirmada"
        RECHAZADA = "rechazada", "Rechazada"

    class Tipo(models.TextChoices):
        TITULAR = "titular", "Titular"
        SUPLENTE = "suplente", "Suplente"

    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="asignacion_autoridad")
    candidatura = models.OneToOneField(CandidaturaAutoridad, on_delete=models.PROTECT, related_name="asignacion", null=True, blank=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="autoridades")
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="asignaciones_autoridad")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.TITULAR)
    orden_suplencia = models.PositiveSmallIntegerField(null=True, blank=True)
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
            if not self.registro_padron.activo:
                raise ValidationError({"registro_padron": "La autoridad debe estar activa en el padron."})
            if self.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id != self.mesa.eleccion_claustro_departamento.eleccion_claustro_id:
                raise ValidationError({"mesa": "La autoridad debe pertenecer al mismo claustro que la mesa."})
            if self.registro_padron.eleccion_claustro_departamento_id != self.mesa.eleccion_claustro_departamento_id:
                raise ValidationError({"mesa": "La autoridad debe pertenecer al mismo departamento que la mesa."})
            if self.registro_padron.sede_id and self.registro_padron.sede_id == self.mesa.sede_id:
                raise ValidationError({"mesa": "El elector no puede ser autoridad en la sede donde cursa."})
            if self.registro_padron.sede_id and not self.registro_padron.turno_cursada_id:
                raise ValidationError({"registro_padron": "El padrón debe tener el turno de cursada antes de asignar esta autoridad."})
            asignacion_sede = getattr(self.registro_padron, "asignacion_sede_padron", None)
            if asignacion_sede and asignacion_sede.sede_id != self.mesa.sede_id:
                raise ValidationError({"mesa": "La autoridad debe asignarse en la sede electoral ya asignada al elector."})
            if self.turno_id and self.registro_padron.turno_cursada_id and self.registro_padron.turno_cursada.se_superpone_con(self.turno):
                raise ValidationError({"turno": "El turno de trabajo se superpone con el turno de cursada."})
            if self.turno_id and not self.turno.elecciones_turno.filter(
                eleccion_claustro_id=self.mesa.eleccion_claustro_departamento.eleccion_claustro_id,
            ).exists():
                raise ValidationError({"turno": "El turno de trabajo debe estar habilitado para el claustro."})


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
