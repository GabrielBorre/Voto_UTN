from django.core.exceptions import ValidationError
from django.db import models, transaction

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
    autoridades_confirmadas_en = models.DateTimeField(null=True, blank=True, editable=False)
    autoridades_confirmadas_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True, editable=False, related_name="confirmaciones_autoridades")
    fecha_limite_justificacion_electores = models.DateField(null=True, blank=True)
    notificaciones_ausentes_confirmadas_en = models.DateTimeField(null=True, blank=True, editable=False)
    justificacion_electores_habilitada_en = models.DateTimeField(null=True, blank=True, editable=False)
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

    def validar_configuracion(self, *, validar_turnos=True):
        if not self.elecciones_sede.exists() or not self.elecciones_claustro.exists():
            raise ValidationError("La elección debe tener sedes y claustros configurados.")
        for eleccion_claustro in self.elecciones_claustro.all():
            if validar_turnos and not eleccion_claustro.turnos_autoridad.exists():
                raise ValidationError("Cada claustro debe tener al menos un turno de autoridades configurado.")
            if not eleccion_claustro.sedes_habilitadas.exists():
                raise ValidationError("Cada claustro debe tener al menos una sede habilitada.")
            for configuracion in eleccion_claustro.departamentos.all():
                if not configuracion.sedes_habilitadas.exists():
                    raise ValidationError("Cada departamento debe tener al menos una sede habilitada.")

    @transaction.atomic
    def cambiar_estado(self, nuevo_estado):
        self.estado = type(self).objects.select_for_update().get(pk=self.pk).estado
        transiciones = {
            self.Estado.EN_PREPARACION: self.Estado.PUBLICADA,
            self.Estado.PUBLICADA: self.Estado.EN_CURSO,
            self.Estado.EN_CURSO: self.Estado.FINALIZADA,
        }
        if transiciones.get(self.estado) != nuevo_estado:
            raise ValidationError("La transicion de estado solicitada no esta permitida.")
        self._validar_estado_unico(nuevo_estado)
        self.validar_configuracion(validar_turnos=nuevo_estado != self.Estado.FINALIZADA)
        if nuevo_estado == self.Estado.EN_CURSO and not self.mesas.exists():
            raise ValidationError("La eleccion debe tener al menos una mesa antes de iniciarse.")
        if nuevo_estado == self.Estado.EN_CURSO:
            from apps.justificativos.models import JustificativoAusencia
            if not self.autoridades_confirmadas_en:
                raise ValidationError("Confirmá las autoridades definitivas antes de iniciar la elección.")
            if self.registros_padron.filter(activo=True, asignacion_mesa__isnull=True).exists():
                raise ValidationError("Todos los electores activos deben tener una mesa asignada antes de iniciar la elección.")
            if JustificativoAusencia.objects.filter(
                registro_padron__eleccion=self, ausencia=JustificativoAusencia.Ausencia.AUTORIDAD,
                estado=JustificativoAusencia.Estado.PENDIENTE,
            ).exists():
                raise ValidationError("Resolvé todos los justificativos de autoridades pendientes antes de iniciar la elección.")
            from apps.autoridades.models import AsignacionAutoridad
            for mesa in self.mesas.select_related("eleccion_claustro_departamento__eleccion_claustro"):
                if not mesa.eleccion_claustro_departamento_id:
                    raise ValidationError(f"La mesa {mesa.numero} no tiene un alcance electoral configurado.")
                claustro = mesa.eleccion_claustro_departamento.eleccion_claustro
                for configuracion in claustro.turnos_autoridad.select_related("turno"):
                    cantidad = AsignacionAutoridad.objects.filter(
                        mesa=mesa, turno=configuracion.turno, tipo="titular", estado="asignada",
                    ).count()
                    if cantidad < configuracion.minimo_titulares_por_mesa:
                        raise ValidationError(
                            f"La mesa {mesa.codigo}, turno {configuracion.turno}, no alcanza el mínimo de autoridades "
                            f"({cantidad} de {configuracion.minimo_titulares_por_mesa})."
                        )
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
    titulares_por_mesa = models.PositiveSmallIntegerField(default=3)
    minimo_titulares_por_mesa = models.PositiveSmallIntegerField(default=1)
    suplentes_por_mesa = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("eleccion_claustro", "turno"), name="turno_unico_por_claustro"),
            models.CheckConstraint(condition=models.Q(suplentes_por_mesa=0), name="turno_sin_suplentes_mesa"),
        ]


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
