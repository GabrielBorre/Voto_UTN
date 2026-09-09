from django.core.exceptions import ValidationError
from django.db import models


class Sede(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_sede"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Claustro(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_claustro"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Turno(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_turno"
        ordering = ("hora_inicio", "nombre")

    def clean(self):
        if self.hora_inicio >= self.hora_fin:
            raise ValidationError({"hora_fin": "Debe ser posterior a la hora de inicio."})

    def __str__(self):
        return self.nombre


class Departamento(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo = models.CharField(max_length=20, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_departamento"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class FechaAdministrativa(models.Model):
    class RolDestinatario(models.TextChoices):
        ADMINISTRADOR_JUNTA = "administrador_junta", "Administrador de junta"
        ADMINISTRATIVO_JUNTA = "administrativo_junta", "Administrativo de junta"
        AUTORIDAD_MESA = "autoridad_mesa", "Autoridad de mesa"
        ELECTOR = "elector", "Elector"

    nombre = models.CharField(max_length=160, unique=True)
    roles_destinatarios = models.JSONField(default=list)
    claustros = models.ManyToManyField(
        Claustro,
        related_name="fechas_administrativas",
        db_table="elecciones_fechaadministrativa_claustros",
    )
    asunto_notificacion = models.CharField(max_length=180)
    mensaje_notificacion = models.TextField()
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_fechaadministrativa"
        ordering = ("nombre",)

    def clean(self):
        roles_validos = {rol for rol, _ in self.RolDestinatario.choices}
        if not self.roles_destinatarios:
            raise ValidationError({"roles_destinatarios": "Debe seleccionar al menos un rol destinatario."})
        if not set(self.roles_destinatarios).issubset(roles_validos):
            raise ValidationError({"roles_destinatarios": "Contiene roles destinatarios invalidos."})

    @property
    def roles_destinatarios_display(self):
        etiquetas = dict(self.RolDestinatario.choices)
        return ", ".join(etiquetas[rol] for rol in self.roles_destinatarios)

    def __str__(self):
        return self.nombre
