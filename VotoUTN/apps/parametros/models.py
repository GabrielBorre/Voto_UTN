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
    class ModalidadSugerida(models.TextChoices):
        FECHA_UNICA = "fecha_unica", "Fecha unica"
        RANGO = "rango", "Rango de fechas"
        DURACION = "duracion", "Duracion desde la fecha de inicio"

    class CriterioDestinatarios(models.TextChoices):
        TODOS_EN_ALCANCE = "todos_en_alcance", "Todos los destinatarios del alcance"
        ELECTORES_ACTIVOS_PADRON = "electores_activos_padron", "Electores activos en el padron"
        ELECTORES_AUSENTES_CONFIRMADOS = "electores_ausentes_confirmados", "Electores con ausencia confirmada"
        AUTORIDADES_ASIGNADAS = "autoridades_asignadas", "Autoridades asignadas"
        AUTORIDADES_AUSENTES_CONFIRMADAS = "autoridades_ausentes_confirmadas", "Autoridades con ausencia confirmada"

    class EventoDisparador(models.TextChoices):
        NINGUNO = "", "Sin evento automatico"
        PUBLICACION_PADRON = "publicacion_padron", "Publicacion de padron"
        AUSENCIA_ELECTORAL = "ausencia_electoral", "Ausencia electoral confirmada"
        AUSENCIA_AUTORIDAD = "ausencia_autoridad", "Ausencia de autoridad confirmada"
        DESIGNACION_AUTORIDAD = "designacion_autoridad", "Designacion de autoridad"
        CAPACITACION_AUTORIDAD = "capacitacion_autoridad", "Capacitacion de autoridades"

    class RolDestinatario(models.TextChoices):
        ADMINISTRADOR_JUNTA = "administrador_junta", "Administrador de junta"
        ADMINISTRATIVO_JUNTA = "administrativo_junta", "Administrativo de junta"
        AUTORIDAD_MESA = "autoridad_mesa", "Autoridad de mesa"
        ELECTOR = "elector", "Elector"

    codigo = models.SlugField(max_length=80, unique=True)
    nombre = models.CharField(max_length=160, unique=True)
    descripcion = models.TextField(blank=True)
    modalidad_sugerida = models.CharField(
        max_length=20,
        choices=ModalidadSugerida.choices,
        default=ModalidadSugerida.FECHA_UNICA,
    )
    duracion_sugerida_dias = models.PositiveSmallIntegerField(null=True, blank=True)
    roles_destinatarios = models.JSONField(default=list)
    claustros = models.ManyToManyField(
        Claustro,
        related_name="fechas_administrativas",
        blank=True,
        db_table="elecciones_fechaadministrativa_claustros",
    )
    alcance_todos_claustros = models.BooleanField(default=True)
    criterio_destinatarios = models.CharField(
        max_length=50,
        choices=CriterioDestinatarios.choices,
        default=CriterioDestinatarios.TODOS_EN_ALCANCE,
    )
    evento_disparador_sugerido = models.CharField(
        max_length=40,
        choices=EventoDisparador.choices,
        blank=True,
        default="",
    )
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
        if self.modalidad_sugerida == self.ModalidadSugerida.DURACION and not self.duracion_sugerida_dias:
            raise ValidationError({"duracion_sugerida_dias": "Debe indicar la duracion sugerida."})
        if self.modalidad_sugerida != self.ModalidadSugerida.DURACION and self.duracion_sugerida_dias:
            raise ValidationError({"duracion_sugerida_dias": "Solo corresponde para la modalidad por duracion."})

    @property
    def roles_destinatarios_display(self):
        etiquetas = dict(self.RolDestinatario.choices)
        return ", ".join(etiquetas[rol] for rol in self.roles_destinatarios)

    def __str__(self):
        return self.nombre
