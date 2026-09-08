from django.core.exceptions import ValidationError
from django.db import models

from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


class Eleccion(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        PREPARADA = "preparada", "Preparada"
        ABIERTA = "abierta", "Abierta"
        CERRADA = "cerrada", "Cerrada"

    nombre = models.CharField("nombre", max_length=180)
    fecha_inicio = models.DateTimeField("inicio")
    fecha_fin = models.DateTimeField("fin")
    fecha_apertura_padron_provisorio = models.DateField(null=True, blank=True)
    fecha_cierre_padron_provisorio = models.DateField(null=True, blank=True)
    fecha_cierre_candidaturas = models.DateField(null=True, blank=True)
    fecha_publicacion_padron_definitivo = models.DateField(null=True, blank=True)
    fecha_limite_justificacion_autoridades = models.DateField(null=True, blank=True)
    fecha_limite_justificacion_electores = models.DateField(null=True, blank=True)
    habilitada = models.BooleanField("habilitada", default=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.BORRADOR)
    maximo_autoridades_por_mesa = models.PositiveSmallIntegerField(default=3)

    class Meta:
        ordering = ["-fecha_inicio"]

    def clean(self):
        if self.fecha_inicio >= self.fecha_fin:
            raise ValidationError({"fecha_fin": "Debe ser posterior a la fecha de inicio."})
        fechas_ordenadas = (
            ("fecha_apertura_padron_provisorio", "fecha_cierre_padron_provisorio"),
            ("fecha_cierre_padron_provisorio", "fecha_publicacion_padron_definitivo"),
            ("fecha_publicacion_padron_definitivo", "fecha_inicio"),
        )
        for inicial, final in fechas_ordenadas:
            valor_inicial = getattr(self, inicial)
            valor_final = getattr(self, final)
            if inicial == "fecha_publicacion_padron_definitivo" and valor_final:
                valor_final = valor_final.date()
            if valor_inicial and valor_final and valor_inicial > valor_final:
                raise ValidationError({final: "Debe ser posterior o igual a la fecha administrativa anterior."})

    def validar_configuracion(self):
        if not self.elecciones_sede.exists() or not self.elecciones_claustro.exists() or not self.elecciones_turno.exists():
            raise ValidationError("La eleccion debe tener sedes, claustros y turnos configurados.")
        for eleccion_claustro in self.elecciones_claustro.all():
            if not eleccion_claustro.sedes_habilitadas.exists():
                raise ValidationError("Cada claustro debe tener al menos una sede habilitada.")
            for configuracion in eleccion_claustro.departamentos.all():
                if not configuracion.sedes_habilitadas.exists():
                    raise ValidationError("Cada departamento debe tener al menos una sede habilitada.")

    def cambiar_estado(self, nuevo_estado):
        transiciones = {
            self.Estado.BORRADOR: self.Estado.PREPARADA,
            self.Estado.PREPARADA: self.Estado.ABIERTA,
            self.Estado.ABIERTA: self.Estado.CERRADA,
        }
        if transiciones.get(self.estado) != nuevo_estado:
            raise ValidationError("La transicion de estado solicitada no esta permitida.")
        self.validar_configuracion()
        if nuevo_estado == self.Estado.ABIERTA and not self.mesas.exists():
            raise ValidationError("La eleccion debe tener al menos una mesa antes de abrirse.")
        self.estado = nuevo_estado
        self.habilitada = nuevo_estado == self.Estado.ABIERTA
        self.save(update_fields=("estado", "habilitada"))

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
    fecha_votacion = models.DateField(null=True, blank=True)
    maximo_votantes_por_mesa = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "claustro"), name="claustro_unico_por_eleccion")]

    def clean(self):
        if self.fecha_votacion and not self.eleccion.fecha_inicio.date() <= self.fecha_votacion <= self.eleccion.fecha_fin.date():
            raise ValidationError({"fecha_votacion": "Debe estar comprendida entre el inicio y el fin de la eleccion."})


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
            raise ValidationError({"sede": "La sede debe estar habilitada para la eleccion."})


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


class FechaAdministrativaEleccion(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="fechas_administrativas")
    fecha_administrativa = models.ForeignKey(FechaAdministrativa, on_delete=models.PROTECT, related_name="programaciones")
    fecha = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "fecha_administrativa"), name="fecha_administrativa_unica_por_eleccion")]

    def clean(self):
        if self.eleccion_id and self.fecha and not self.eleccion.fecha_inicio.date() <= self.fecha <= self.eleccion.fecha_fin.date():
            raise ValidationError({"fecha": "Debe estar comprendida entre el inicio y el fin de la eleccion."})
