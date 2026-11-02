from django.core.exceptions import ValidationError
from django.db import models

from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.parametros.models import Sede, Turno


class ConfiguracionAutoridades(models.Model):
    class Modo(models.TextChoices):
        NOMINA = "nomina", "Nómina común"
        ALEATORIO = "aleatorio", "Sorteo por mesa"

    eleccion_claustro = models.OneToOneField("elecciones.EleccionClaustro", on_delete=models.PROTECT, related_name="configuracion_autoridades")
    modo = models.CharField(max_length=12, choices=Modo.choices, default=Modo.NOMINA)
    permitir_cambio_sede = models.BooleanField(default=False)
    reacomodar_titulares = models.BooleanField(default=False)
    permitir_mesa_distinta = models.BooleanField(default=False)


class CandidaturaAutoridad(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="candidatura_autoridad")
    cargada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="candidaturas_autoridad_cargadas")
    cargada_en = models.DateTimeField(auto_now_add=True)
    excluida = models.BooleanField(default=False)
    mesa_manual = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name="selecciones_autoridad")
    turno_manual = models.ForeignKey(Turno, on_delete=models.PROTECT, null=True, blank=True)
    tipo_manual = models.CharField(max_length=12, choices=(("titular", "Titular"), ("suplente", "Suplente")), blank=True)
    orden_manual = models.PositiveSmallIntegerField(null=True, blank=True)
    mesa_traslado = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name="traslados_autoridad")
    turno_traslado = models.ForeignKey(Turno, on_delete=models.PROTECT, null=True, blank=True, related_name="traslados_autoridad")

    class Meta:
        db_table = "elecciones_candidaturaautoridad"

    def __str__(self):
        elector = self.registro_padron.elector
        return f"{elector.nombre_completo} · DNI {elector.dni} · Legajo {elector.legajo}"


class AsignacionAutoridad(models.Model):
    class Estado(models.TextChoices):
        ASIGNADA = "asignada", "Asignada"
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
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.ASIGNADA)
    asignada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="autoridades_asignadas")
    asignada_en = models.DateTimeField(auto_now_add=True)
    respondida_en = models.DateTimeField(null=True, blank=True)
    reemplazo_confirmado_en = models.DateTimeField(null=True, blank=True)
    reemplazo_confirmado_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True, related_name="reemplazos_autoridad_confirmados")
    reemplazada_por = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reemplazos_realizados")

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
            from apps.autoridades.distribucion import es_candidato_electoral
            if es_candidato_electoral(self.registro_padron):
                raise ValidationError({"registro_padron": "Un candidato electoral no puede ser autoridad de mesa."})
            if self.registro_padron.sede_id and not self.registro_padron.turno_cursada_id:
                raise ValidationError({"registro_padron": "Completá el horario de asistencia a la sede antes de asignar esta autoridad."})
            asignacion_sede = getattr(self.registro_padron, "asignacion_sede_padron", None)
            traslado_confirmado = self.candidatura_id and self.candidatura.mesa_traslado_id == self.mesa_id and self.candidatura.turno_traslado_id == self.turno_id
            if asignacion_sede and asignacion_sede.sede_id != self.mesa.sede_id and not traslado_confirmado:
                raise ValidationError({"mesa": "La autoridad debe asignarse en la sede electoral ya asignada al elector."})
            if self.turno_id and self.registro_padron.turno_cursada_id and self.registro_padron.turno_cursada.se_superpone_con(self.turno):
                raise ValidationError({"turno": "El turno de trabajo se superpone con el horario de asistencia a la sede."})
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
