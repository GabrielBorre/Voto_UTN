from django.core.exceptions import ValidationError
from django.db import models

from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


ESTADOS_ELECCION_NO_CERRADOS = ("en_preparacion", "publicada", "en_curso")
ESTADOS_CONFIGURACION_SOLO_LECTURA = ("publicada", "en_curso", "finalizada")


class Eleccion(models.Model):
    class Estado(models.TextChoices):
        EN_PREPARACION = "en_preparacion", "En preparación"
        PUBLICADA = "publicada", "Publicada"
        EN_CURSO = "en_curso", "En curso"
        FINALIZADA = "finalizada", "Finalizada"

    nombre = models.CharField("nombre", max_length=180)
    fecha_inicio = models.DateField("fecha de inicio del proceso")
    fecha_fin = models.DateField("fecha de fin del proceso")
    fecha_apertura_padron_provisorio = models.DateField(null=True, blank=True)
    fecha_cierre_padron_provisorio = models.DateField(null=True, blank=True)
    fecha_cierre_candidaturas = models.DateField(null=True, blank=True)
    fecha_publicacion_padron_definitivo = models.DateField(null=True, blank=True)
    fecha_cierre_solicitudes_cambio_sede = models.DateField(null=True, blank=True)
    fecha_limite_justificacion_autoridades = models.DateField(null=True, blank=True)
    fecha_limite_justificacion_electores = models.DateField(null=True, blank=True)
    notificaciones_ausentes_confirmadas_en = models.DateTimeField(null=True, blank=True, editable=False)
    habilitada = models.BooleanField("habilitada", default=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.EN_PREPARACION)
    maximo_autoridades_por_mesa = models.PositiveSmallIntegerField(default=3)

    class Meta:
        ordering = ["-fecha_inicio"]
        constraints = [
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(estado__in=ESTADOS_ELECCION_NO_CERRADOS),
                name="una_eleccion_no_cerrada",
            ),
        ]

    def _validar_estado_unico(self, estado=None):
        estado_a_validar = estado or self.estado
        if estado_a_validar in ESTADOS_ELECCION_NO_CERRADOS:
            elecciones_existentes = type(self).objects.filter(
                estado__in=ESTADOS_ELECCION_NO_CERRADOS,
            ).exclude(pk=self.pk)
            if elecciones_existentes.exists():
                raise ValidationError("Ya existe una elección que no está cerrada.")

    def clean(self):
        self._validar_estado_unico()
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError({"fecha_fin": "Debe ser igual o posterior a la fecha de inicio."})
        fechas_ordenadas = (
            ("fecha_apertura_padron_provisorio", "fecha_cierre_padron_provisorio"),
            ("fecha_cierre_padron_provisorio", "fecha_publicacion_padron_definitivo"),
            ("fecha_publicacion_padron_definitivo", "fecha_inicio"),
            ("fecha_inicio", "fecha_cierre_solicitudes_cambio_sede"),
        )
        for inicial, final in fechas_ordenadas:
            valor_inicial = getattr(self, inicial)
            valor_final = getattr(self, final)
            if valor_inicial and valor_final and valor_inicial > valor_final:
                raise ValidationError({final: "Debe ser posterior o igual a la fecha administrativa anterior."})

    def validar_configuracion(self):
        if not self.elecciones_sede.exists() or not self.elecciones_claustro.exists():
            raise ValidationError("La elección debe tener sedes y claustros configurados.")
        for eleccion_claustro in self.elecciones_claustro.all():
            if not eleccion_claustro.turnos_autoridad.exists():
                raise ValidationError("Cada claustro debe tener al menos un turno de autoridades configurado.")
            if not eleccion_claustro.sedes_habilitadas.exists():
                raise ValidationError("Cada claustro debe tener al menos una sede habilitada.")
            for configuracion in eleccion_claustro.departamentos.all():
                if not configuracion.sedes_habilitadas.exists():
                    raise ValidationError("Cada departamento debe tener al menos una sede habilitada.")

    def cambiar_estado(self, nuevo_estado):
        transiciones = {
            self.Estado.EN_PREPARACION: self.Estado.PUBLICADA,
            self.Estado.PUBLICADA: self.Estado.EN_CURSO,
            self.Estado.EN_CURSO: self.Estado.FINALIZADA,
        }
        if transiciones.get(self.estado) != nuevo_estado:
            raise ValidationError("La transicion de estado solicitada no esta permitida.")
        from django.utils import timezone
        if self.mensajes_programados.filter(estado_eleccion=self.estado, habilitado=True, procesado_en__isnull=True, programado_para__gt=timezone.now()).exists():
            raise ValidationError("Hay mensajes futuros pendientes en el estado actual. Reprográmelos o desactívelos antes de avanzar.")
        self._validar_estado_unico(nuevo_estado)
        self.validar_configuracion()
        if nuevo_estado == self.Estado.EN_CURSO and not self.mesas.exists():
            raise ValidationError("La eleccion debe tener al menos una mesa antes de iniciarse.")
        if nuevo_estado == self.Estado.PUBLICADA:
            claustros_sin_padron = self.elecciones_claustro.exclude(
                departamentos__registros_padron__activo=True
            )
            if claustros_sin_padron.exists():
                raise ValidationError("Debe existir al menos una importación de padrón válida por cada claustro antes de publicar la elección.")
        self.estado = nuevo_estado
        self.habilitada = nuevo_estado in (self.Estado.PUBLICADA, self.Estado.EN_CURSO)
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
    organizacion_departamentos = models.CharField(
        max_length=24,
        choices=Claustro.OrganizacionDepartamentos.choices,
        default=Claustro.OrganizacionDepartamentos.POR_DEPARTAMENTO,
    )
    fecha_votacion = models.DateField(null=True, blank=True)
    maximo_votantes_por_mesa = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "claustro"), name="claustro_unico_por_eleccion")]

    def clean(self):
        if self.fecha_votacion and not self.eleccion.fecha_inicio <= self.fecha_votacion <= self.eleccion.fecha_fin:
            raise ValidationError({"fecha_votacion": "Debe estar comprendida entre el inicio y el fin de la eleccion."})


class EleccionClaustroTurno(models.Model):
    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="turnos_autoridad")
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="elecciones_turno")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion_claustro", "turno"), name="turno_unico_por_claustro")]


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
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="elecciones_claustro_departamento",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("eleccion_claustro", "departamento"),
                condition=models.Q(departamento__isnull=False),
                name="departamento_unico_por_claustro",
            ),
            models.UniqueConstraint(
                fields=("eleccion_claustro",),
                condition=models.Q(departamento__isnull=True),
                name="alcance_sin_departamento_unico_por_claustro",
            ),
        ]

    @property
    def nombre_alcance(self):
        return str(self.departamento) if self.departamento_id else "Sin distinción por departamento"

    def __str__(self):
        return f"{self.eleccion_claustro.claustro} / {self.nombre_alcance}"


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
        if self.eleccion_id and self.fecha and not self.eleccion.fecha_inicio <= self.fecha <= self.eleccion.fecha_fin:
            raise ValidationError({"fecha": "Debe estar comprendida entre el inicio y el fin de la eleccion."})
