import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Sede(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo = models.CharField(max_length=20, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Claustro(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo = models.CharField(max_length=20, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Turno(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    activo = models.BooleanField(default=True)

    class Meta:
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
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Eleccion(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        PREPARADA = "preparada", "Preparada"
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"

    nombre = models.CharField("nombre", max_length=180)
    fecha_inicio = models.DateTimeField("inicio")
    fecha_fin = models.DateTimeField("fin")
    habilitada = models.BooleanField("habilitada", default=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.BORRADOR)

    class Meta:
        ordering = ["-fecha_inicio"]

    def clean(self):
        if self.fecha_inicio >= self.fecha_fin:
            raise ValidationError({"fecha_fin": "Debe ser posterior a la fecha de inicio."})

    def __str__(self):
        return self.nombre


class EleccionSede(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="elecciones_sede")
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="elecciones_sede")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "sede"), name="sede_unica_por_eleccion")]


class EleccionClaustro(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="elecciones_claustro")
    claustro = models.ForeignKey(Claustro, on_delete=models.PROTECT, related_name="elecciones_claustro")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "claustro"), name="claustro_unico_por_eleccion")]


class EleccionTurno(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="elecciones_turno")
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="elecciones_turno")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "turno"), name="turno_unico_por_eleccion")]


class EleccionClaustroSede(models.Model):
    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="sedes_habilitadas")
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="elecciones_claustro_sede")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion_claustro", "sede"), name="sede_unica_por_claustro")]

    def clean(self):
        if self.eleccion_claustro_id and not EleccionSede.objects.filter(eleccion=self.eleccion_claustro.eleccion, sede=self.sede).exists():
            raise ValidationError({"sede": "La sede debe estar habilitada para la elección."})


class EleccionClaustroDepartamento(models.Model):
    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="departamentos")
    departamento = models.ForeignKey(Departamento, on_delete=models.PROTECT, related_name="elecciones_claustro_departamento")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion_claustro", "departamento"), name="departamento_unico_por_claustro")]


class EleccionClaustroDepartamentoSede(models.Model):
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="sedes_habilitadas")
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="elecciones_departamento_sede")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion_claustro_departamento", "sede"), name="sede_unica_por_departamento")]

    def clean(self):
        if self.eleccion_claustro_departamento_id and not EleccionClaustroSede.objects.filter(eleccion_claustro=self.eleccion_claustro_departamento.eleccion_claustro, sede=self.sede).exists():
            raise ValidationError({"sede": "La sede debe estar habilitada para el claustro."})


class Mesa(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="mesas")
    numero = models.PositiveIntegerField("numero")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)

    class Meta:
        ordering = ["eleccion_id", "numero"]
        constraints = [models.UniqueConstraint(fields=("eleccion", "numero"), name="unique_mesa_per_eleccion")]

    def clean(self):
        if self.eleccion_claustro_departamento_id and self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma elección."})
        if self.eleccion_claustro_departamento_id and self.sede_id and not EleccionClaustroDepartamentoSede.objects.filter(eleccion_claustro_departamento=self.eleccion_claustro_departamento, sede=self.sede).exists():
            raise ValidationError({"sede": "La sede debe estar habilitada para el departamento."})
        if self.eleccion_id and self.turno_id and not EleccionTurno.objects.filter(eleccion_id=self.eleccion_id, turno_id=self.turno_id).exists():
            raise ValidationError({"turno": "El turno debe estar habilitado para la eleccion."})

    def __str__(self):
        return f"{self.eleccion} - Mesa {self.numero}"


class Elector(models.Model):
    legajo = models.CharField("legajo", max_length=20, unique=True)
    nombre = models.CharField("nombre", max_length=180)
    dni = models.CharField("DNI", max_length=12, unique=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="electores", null=True, blank=True)

    class Meta:
        ordering = ["legajo"]

    def __str__(self):
        return f"{self.legajo} - {self.nombre}"


class RegistroPadron(models.Model):
    elector = models.ForeignKey(Elector, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="registros_padron")
    activo = models.BooleanField(default=True)
    identificador_qr = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("elector", "eleccion"), name="elector_unico_por_eleccion")]

    def clean(self):
        if self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma elección."})


class AsignacionMesa(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="asignacion_mesa")
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="asignaciones_padron")

    def clean(self):
        if self.registro_padron_id and self.mesa_id and self.registro_padron.eleccion_id != self.mesa.eleccion_id:
            raise ValidationError({"mesa": "Debe pertenecer a la misma elección del padrón."})
