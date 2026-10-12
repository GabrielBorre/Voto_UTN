import secrets
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.parametros.models import Sede, Departamento


class Elector(models.Model):
    legajo = models.CharField("legajo", max_length=20, unique=True)
    nombre = models.CharField("nombre", max_length=180)
    apellido = models.CharField("apellido", max_length=180, blank=True)
    dni = models.CharField("DNI", max_length=12, unique=True)
    tipo_documento = models.CharField("tipo documento", max_length=30, default="DNI")
    correo_electronico = models.EmailField("correo electronico", blank=True)
    tiene_discapacidad = models.BooleanField("tiene discapacidad", default=False)
    departamento_principal = models.ForeignKey(Departamento, on_delete=models.PROTECT, null=True, blank=True, related_name="electores_principal")

    class Meta:
        db_table = "elecciones_elector"
        ordering = ["legajo"]

    def __str__(self):
        return f"{self.legajo} - {self.nombre_completo}"

    @property
    def nombre_completo(self):
        return " ".join(parte for parte in (self.nombre, self.apellido) if parte).strip()


class RegistroPadron(models.Model):
    ALFABETO_CODIGO_QR = string.ascii_uppercase + string.digits
    LONGITUD_CODIGO_QR = 8

    elector = models.ForeignKey(Elector, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="registros_padron")
    sede = models.ForeignKey("parametros.Sede", on_delete=models.PROTECT, related_name="registros_padron", null=True, blank=True, verbose_name="sede donde cursa")
    nivel = models.CharField(max_length=50, blank=True)
    activo = models.BooleanField(default=True)
    identificador_qr = models.CharField(max_length=LONGITUD_CODIGO_QR, unique=True, blank=True, editable=False)
    qr_generado_en = models.DateTimeField(null=True, blank=True, editable=False)
    numero_mesa_qr = models.PositiveIntegerField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "elecciones_registropadron"
        constraints = [models.UniqueConstraint(fields=("elector", "eleccion"), name="elector_unico_por_eleccion")]

    def clean(self):
        self.validar_sede()
        if self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma eleccion."})

    def validar_sede(self):
        if self.sede_id and not self.sede.activa:
            raise ValidationError({"sede": "La sede donde cursa debe estar activa."})

    @classmethod
    def generar_codigo_qr_corto(cls):
        return "".join(secrets.choice(cls.ALFABETO_CODIGO_QR) for _ in range(cls.LONGITUD_CODIGO_QR))

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = RegistroPadron.objects.filter(pk=self.pk).only(
                "qr_generado_en", "eleccion_id", "eleccion_claustro_departamento_id", "sede_id", "activo"
            ).first()
            if anterior and anterior.qr_generado_en and any(
                getattr(anterior, campo) != getattr(self, campo)
                for campo in ("eleccion_id", "eleccion_claustro_departamento_id", "sede_id", "activo")
            ):
                raise ValidationError("No se puede modificar el alcance del padrón después de emitir su QR.")
        if not self.identificador_qr:
            for _ in range(12):
                candidato = self.generar_codigo_qr_corto()
                if not RegistroPadron.objects.filter(identificador_qr=candidato).exclude(pk=self.pk).exists():
                    self.identificador_qr = candidato
                    break
            else:
                raise ValidationError({"identificador_qr": "No se pudo generar un codigo QR unico."})
        super().save(*args, **kwargs)


class ImportacionPadron(models.Model):
    class Estado(models.TextChoices):
        PREVISUALIZADA = "previsualizada", "Previsualizada"
        CONFIRMADA = "confirmada", "Confirmada"
        RECHAZADA = "rechazada", "Rechazada"
        PADRON_ELIMINADO = "padron_eliminado", "Padrón eliminado"

    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="importaciones_padron")
    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="importaciones_padron")
    archivo = models.FileField(upload_to="padrones/%Y/%m/%d")
    nombre_archivo = models.CharField(max_length=255)
    huella_archivo = models.CharField(max_length=64)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PREVISUALIZADA)
    cantidad_filas = models.PositiveIntegerField(default=0)
    cantidad_validas = models.PositiveIntegerField(default=0)
    cantidad_errores = models.PositiveIntegerField(default=0)
    creada_en = models.DateTimeField(auto_now_add=True)
    confirmada_en = models.DateTimeField(null=True, blank=True)
    usuario = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="importaciones_padron")

    class Meta:
        db_table = "elecciones_importacionpadron"
        ordering = ("-creada_en",)

    def clean(self):
        if self.eleccion_claustro_id and self.eleccion_id != self.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro": "Debe pertenecer a la misma eleccion."})


class ErrorImportacionPadron(models.Model):
    importacion = models.ForeignKey(ImportacionPadron, on_delete=models.CASCADE, related_name="errores")
    fila = models.PositiveIntegerField(null=True, blank=True)
    campo = models.CharField(max_length=64, blank=True)
    mensaje = models.CharField(max_length=300)

    class Meta:
        db_table = "elecciones_errorimportacionpadron"
        ordering = ("fila", "id")


class EmisionPadronImprimible(models.Model):
    class Estado(models.TextChoices):
        VIGENTE = "vigente", "Vigente"
        INVALIDADA = "invalidada", "Invalidada"

    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="emisiones_padron")
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.VIGENTE)
    emitida_en = models.DateTimeField(auto_now_add=True)
    emitida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="emisiones_padron_realizadas")
    invalidada_en = models.DateTimeField(null=True, blank=True)
    invalidada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="emisiones_padron_invalidadas")
    motivo_invalidacion = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-emitida_en",)
        constraints = [
            models.UniqueConstraint(
                fields=("eleccion_claustro",),
                condition=models.Q(estado="vigente"),
                name="emision_vigente_unica_por_claustro",
            )
        ]


class PadronVotacion(models.Model):
    """Conjunto manual de cargos y reglas que determina una boleta/padrón electoral."""

    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="padrones_votacion")
    nombre = models.CharField(max_length=180)
    puestos = models.ManyToManyField("partidos.PuestoEleccion", through="PuestoPadronVotacion", related_name="padrones_votacion")
    calculado_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nombre", "id")
        constraints = [models.UniqueConstraint(fields=("eleccion_claustro", "nombre"), name="padron_votacion_nombre_unico")]

    def __str__(self):
        return f"{self.eleccion_claustro.claustro} · {self.nombre}"


class PuestoPadronVotacion(models.Model):
    padron_votacion = models.ForeignKey(PadronVotacion, on_delete=models.CASCADE, related_name="puestos_configurados")
    puesto_eleccion = models.ForeignKey("partidos.PuestoEleccion", on_delete=models.PROTECT, related_name="configuraciones_padron_votacion")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("padron_votacion", "puesto_eleccion"), name="puesto_unico_por_padron_votacion")]

    def clean(self):
        if self.padron_votacion_id and self.puesto_eleccion_id and self.puesto_eleccion.eleccion_claustro_id != self.padron_votacion.eleccion_claustro_id:
            raise ValidationError({"puesto_eleccion": "El cargo debe pertenecer al mismo claustro."})


class GrupoInclusionPadronVotacion(models.Model):
    padron_votacion = models.ForeignKey(PadronVotacion, on_delete=models.CASCADE, related_name="grupos_inclusion")
    orden = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("orden", "id")


class BaseCondicionPadron(models.Model):
    class Campo(models.TextChoices):
        DEPARTAMENTO = "departamento", "Departamento"
        DEPARTAMENTO_PRINCIPAL = "departamento_principal", "Departamento principal"
        NIVEL = "nivel", "Nivel"
        SEDE_DONDE_CURSA = "sede_donde_cursa", "Sede donde cursa"
        DISCAPACIDAD = "discapacidad", "Tiene discapacidad"

    class Operador(models.TextChoices):
        IGUAL = "igual", "Es igual a"
        EN = "en", "Está incluido en"
        MAYOR = "mayor", "Es mayor que"
        MAYOR_IGUAL = "mayor_igual", "Es mayor o igual que"
        MENOR = "menor", "Es menor que"
        MENOR_IGUAL = "menor_igual", "Es menor o igual que"

    campo = models.CharField(max_length=32, choices=Campo.choices)
    operador = models.CharField(max_length=16, choices=Operador.choices)
    valor = models.CharField(max_length=500, help_text="Para 'Está incluido en', separe los valores con comas.")

    class Meta:
        abstract = True

    def clean(self):
        operadores_numericos = {self.Operador.IGUAL, self.Operador.MAYOR, self.Operador.MAYOR_IGUAL, self.Operador.MENOR, self.Operador.MENOR_IGUAL}
        if self.campo == self.Campo.NIVEL:
            if self.operador not in operadores_numericos:
                raise ValidationError({"operador": "Nivel solo admite comparadores numéricos."})
            try:
                int(self.valor)
            except (TypeError, ValueError):
                raise ValidationError({"valor": "Nivel debe ser un número entero."})
        elif self.campo == self.Campo.DISCAPACIDAD:
            if self.operador != self.Operador.IGUAL or self.valor.casefold() not in {"si", "no"}:
                raise ValidationError({"valor": "Discapacidad solo admite Sí o No."})
        elif self.operador not in {self.Operador.IGUAL, self.Operador.EN}:
            raise ValidationError({"operador": "Este campo solo admite igualdad o pertenencia."})


class CondicionInclusionPadronVotacion(BaseCondicionPadron):
    grupo = models.ForeignKey(GrupoInclusionPadronVotacion, on_delete=models.CASCADE, related_name="condiciones")


class ConfiguracionSedePadronVotacion(models.Model):
    padron_votacion = models.ForeignKey(PadronVotacion, on_delete=models.CASCADE, related_name="configuraciones_sede")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="configuraciones_padron_votacion")
    sede_predeterminada = models.ForeignKey(EleccionClaustroDepartamentoSede, on_delete=models.PROTECT, related_name="configuraciones_predeterminadas_padron")

    class Meta:
        constraints = [models.UniqueConstraint(fields=("padron_votacion", "eleccion_claustro_departamento"), name="config_sede_unica_por_padron_depto")]

    def clean(self):
        errores = {}
        if self.padron_votacion_id and self.eleccion_claustro_departamento_id and self.padron_votacion.eleccion_claustro_id != self.eleccion_claustro_departamento.eleccion_claustro_id:
            errores["eleccion_claustro_departamento"] = "El departamento debe pertenecer al claustro del padrón de votación."
        if self.sede_predeterminada_id and self.sede_predeterminada.eleccion_claustro_departamento_id != self.eleccion_claustro_departamento_id:
            errores["sede_predeterminada"] = "La sede debe estar habilitada para el departamento seleccionado."
        if errores:
            raise ValidationError(errores)


class ReglaAsignacionSede(BaseCondicionPadron):
    configuracion = models.ForeignKey(ConfiguracionSedePadronVotacion, on_delete=models.CASCADE, related_name="reglas")
    orden = models.PositiveSmallIntegerField(default=1)
    sede_destino = models.ForeignKey(EleccionClaustroDepartamentoSede, on_delete=models.PROTECT, related_name="reglas_asignacion_padron")

    class Meta:
        ordering = ("orden", "id")

    def clean(self):
        super().clean()
        if self.sede_destino_id and self.sede_destino.eleccion_claustro_departamento_id != self.configuracion.eleccion_claustro_departamento_id:
            raise ValidationError({"sede_destino": "La sede destino debe estar habilitada para este departamento."})


class AsignacionPadronVotacion(models.Model):
    padron_votacion = models.ForeignKey(PadronVotacion, on_delete=models.CASCADE, related_name="asignaciones")
    registro_padron = models.ForeignKey(RegistroPadron, on_delete=models.PROTECT, related_name="asignaciones_padrones_votacion")
    sede_asignada = models.ForeignKey(EleccionClaustroDepartamentoSede, on_delete=models.PROTECT, related_name="asignaciones_padrones_votacion")
    calculada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("padron_votacion", "registro_padron")
        constraints = [models.UniqueConstraint(fields=("padron_votacion", "registro_padron"), name="registro_unico_por_padron_votacion")]

    def clean(self):
        errores = {}
        if self.padron_votacion_id and self.registro_padron_id and self.padron_votacion.eleccion_claustro_id != self.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id:
            errores["registro_padron"] = "El elector debe pertenecer al mismo claustro."
        if self.registro_padron_id and self.sede_asignada_id and self.sede_asignada.eleccion_claustro_departamento_id != self.registro_padron.eleccion_claustro_departamento_id:
            errores["sede_asignada"] = "La sede asignada debe estar habilitada para el departamento del elector."
        if errores:
            raise ValidationError(errores)


class ConfiguracionSedesClaustro(models.Model):
    eleccion_claustro = models.OneToOneField(
        EleccionClaustro,
        on_delete=models.CASCADE,
        related_name="configuracion_sedes_padron",
    )
    actualizada_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reglas de sede · {self.eleccion_claustro}"


class ReglaSedeClaustro(BaseCondicionPadron):
    configuracion = models.ForeignKey(
        ConfiguracionSedesClaustro,
        on_delete=models.CASCADE,
        related_name="reglas",
    )
    orden = models.PositiveSmallIntegerField()
    sede_destino = models.ForeignKey(
        "parametros.Sede",
        on_delete=models.PROTECT,
        related_name="reglas_sede_claustro",
    )
    aplicar_a_todos = models.BooleanField(default=True)
    alcances_especificos = models.ManyToManyField(
        EleccionClaustroDepartamento,
        blank=True,
        related_name="reglas_sede_claustro",
    )

    class Meta:
        ordering = ("orden", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("configuracion", "orden"),
                name="orden_unico_regla_sede_claustro",
            )
        ]

    def clean(self):
        super().clean()
        if not self.configuracion_id or not self.sede_destino_id:
            return
        sedes_habilitadas = EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=self.configuracion.eleccion_claustro,
            sede=self.sede_destino,
            sede__activa=True,
        )
        if self.pk and not self.aplicar_a_todos:
            sedes_habilitadas = sedes_habilitadas.filter(
                eleccion_claustro_departamento__in=self.alcances_especificos.all(),
            )
        if not sedes_habilitadas.exists():
            raise ValidationError({"sede_destino": "La sede debe estar habilitada en al menos un alcance del claustro."})


class AsignacionSedePadron(models.Model):
    class Estado(models.TextChoices):
        ASIGNADA = "asignada", "Sede asignada"
        PENDIENTE = "pendiente", "Requiere una regla"

    registro_padron = models.OneToOneField(
        RegistroPadron,
        on_delete=models.CASCADE,
        related_name="asignacion_sede_padron",
    )
    sede = models.ForeignKey(
        "parametros.Sede",
        on_delete=models.PROTECT,
        related_name="asignaciones_sede_padron",
        null=True,
        blank=True,
    )
    regla_aplicada = models.ForeignKey(
        ReglaSedeClaustro,
        on_delete=models.SET_NULL,
        related_name="asignaciones_generadas",
        null=True,
        blank=True,
    )
    estado = models.CharField(max_length=12, choices=Estado.choices)
    calculada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("registro_padron__eleccion_claustro_departamento__departamento__nombre", "registro_padron__elector__apellido", "registro_padron__elector__nombre")

    def clean(self):
        if self.sede_id and not EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento=self.registro_padron.eleccion_claustro_departamento,
            sede_id=self.sede_id,
        ).exists():
            raise ValidationError({"sede": "La sede debe estar habilitada para el alcance del elector."})
