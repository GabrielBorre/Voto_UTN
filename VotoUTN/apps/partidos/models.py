from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.conf import settings
from django.db import models

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import Elector


class Partido(models.Model):
    nombre = models.CharField(max_length=180, unique=True)
    sigla = models.CharField(max_length=32, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return f"{self.nombre} ({self.sigla})" if self.sigla else self.nombre


class OrganoElectivo(models.Model):
    nombre = models.CharField(max_length=160, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class CargoElectivo(models.Model):
    organo = models.ForeignKey(
        OrganoElectivo,
        on_delete=models.PROTECT,
        related_name="cargos",
    )
    nombre = models.CharField(max_length=120)
    permite_filtrar_claustros = models.BooleanField(
        "permite limitar por claustros",
        default=True,
        help_text="Permite elegir solo algunos claustros; si no se usa el filtro, se incluyen todos los de la elección.",
    )
    descripcion = models.TextField(blank=True)
    permite_filtrar_departamentos = models.BooleanField(
        "permite limitar por departamentos",
        default=False,
        help_text="Permite elegir solo algunos departamentos; funciona independientemente del filtro por claustros.",
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("organo__nombre", "nombre")
        constraints = [
            models.UniqueConstraint(fields=("organo", "nombre"), name="cargo_unico_por_organo")
        ]

    def __str__(self):
        return f"{self.nombre} - {self.organo.nombre}"

class ParticipacionPartido(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="partidos_participantes")
    partido = models.ForeignKey(
        Partido,
        on_delete=models.SET_NULL,
        related_name="participaciones",
        null=True,
        blank=True,
        help_text="Referencia histórica opcional; la presentación electoral no depende de una agrupación permanente.",
    )
    codigo_presentacion = models.CharField(
        max_length=80,
        blank=True,
        help_text="Código interno de agrupación de filas del CSV; las presentaciones históricas pueden no tenerlo.",
    )
    eleccion_claustro = models.ForeignKey(
        EleccionClaustro,
        on_delete=models.PROTECT,
        related_name="presentaciones_listas",
        null=True,
        blank=True,
    )
    numero_lista = models.CharField(max_length=20)
    nombre_lista = models.CharField(max_length=180, blank=True)
    apoderado_nombre = models.CharField(max_length=180, blank=True)
    apoderado_email = models.EmailField(blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("eleccion_claustro__claustro__nombre", "numero_lista", "nombre_lista")
        constraints = [
            models.UniqueConstraint(
                fields=("eleccion", "codigo_presentacion"),
                condition=~models.Q(codigo_presentacion=""),
                name="presentacion_unica_por_eleccion",
            ),
        ]

    def __str__(self):
        return f"Lista {self.numero_lista} - {self.nombre_lista or self.partido or self.codigo_presentacion}"

    def clean(self):
        if self.eleccion_claustro_id and self.eleccion_claustro.eleccion_id != self.eleccion_id:
            raise ValidationError({"eleccion_claustro": "El claustro debe pertenecer a la elección."})


class PuestoEleccion(models.Model):
    puesto = models.ForeignKey(CargoElectivo, on_delete=models.PROTECT, related_name="configuraciones_eleccion")
    eleccion_claustro = models.ForeignKey(
        EleccionClaustro,
        on_delete=models.PROTECT,
        related_name="puestos_electivos",
    )
    eleccion_claustro_departamento = models.ForeignKey(
        EleccionClaustroDepartamento,
        on_delete=models.PROTECT,
        related_name="puestos_electivos",
        null=True,
        blank=True,
    )
    cantidad_titulares = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    cantidad_suplentes = models.PositiveSmallIntegerField(default=0)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = (
            "eleccion_claustro__claustro__nombre",
            "eleccion_claustro_departamento__departamento__nombre",
            "puesto__organo__nombre",
            "puesto__nombre",
        )
        constraints = [
            models.UniqueConstraint(
                fields=("eleccion_claustro", "puesto"),
                condition=models.Q(eleccion_claustro_departamento__isnull=True),
                name="puesto_unico_por_claustro",
            ),
            models.UniqueConstraint(
                fields=("eleccion_claustro_departamento", "puesto"),
                condition=models.Q(eleccion_claustro_departamento__isnull=False),
                name="puesto_unico_por_departamento",
            ),
        ]

    @property
    def eleccion(self):
        return self.eleccion_claustro.eleccion

    def clean(self):
        errores = {}
        if self.eleccion_claustro_departamento_id:
            if self.eleccion_claustro_departamento.eleccion_claustro_id != self.eleccion_claustro_id:
                errores["eleccion_claustro_departamento"] = "El departamento debe pertenecer al claustro seleccionado."
            if self.puesto_id and not self.puesto.permite_filtrar_departamentos:
                errores["eleccion_claustro_departamento"] = "Este puesto no admite configuración por departamento."
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        alcance = str(self.eleccion_claustro.claustro)
        if self.eleccion_claustro_departamento_id:
            alcance += f" / {self.eleccion_claustro_departamento.departamento}"
        return f"{self.puesto} — {alcance}"


class ListaCandidatos(models.Model):
    participacion = models.ForeignKey(ParticipacionPartido, on_delete=models.PROTECT, related_name="listas")
    eleccion_claustro = models.ForeignKey(EleccionClaustro, on_delete=models.PROTECT, related_name="listas_candidatos")
    eleccion_claustro_departamento = models.ForeignKey(
        EleccionClaustroDepartamento,
        on_delete=models.PROTECT,
        related_name="listas_candidatos",
        null=True,
        blank=True,
    )
    nombre = models.CharField(max_length=180)
    puesto_eleccion = models.ForeignKey(
        PuestoEleccion,
        on_delete=models.PROTECT,
        related_name="listas_candidatos",
        null=True,
        blank=True,
        help_text="Las listas históricas pueden no tener un puesto estructurado asociado.",
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("eleccion_claustro__claustro__nombre", "nombre")
        constraints = [
            models.UniqueConstraint(
                fields=("participacion", "puesto_eleccion"),
                condition=models.Q(puesto_eleccion__isnull=False),
                name="lista_unica_por_presentacion_y_puesto",
            ),
        ]

    def clean(self):
        errores = {}
        if self.participacion_id and self.eleccion_claustro_id:
            if self.participacion.eleccion_id != self.eleccion_claustro.eleccion_id:
                errores["eleccion_claustro"] = "El claustro debe pertenecer a la eleccion del partido."
            elif (
                self.participacion.eleccion_claustro_id
                and self.participacion.eleccion_claustro_id != self.eleccion_claustro_id
            ):
                errores["eleccion_claustro"] = "La candidatura debe pertenecer al claustro de la presentación."
        if self.eleccion_claustro_departamento_id and self.eleccion_claustro_id:
            if self.eleccion_claustro_departamento.eleccion_claustro_id != self.eleccion_claustro_id:
                errores["eleccion_claustro_departamento"] = "El departamento debe pertenecer al claustro seleccionado."
        if self.puesto_eleccion_id:
            if self.puesto_eleccion.eleccion_claustro_id != self.eleccion_claustro_id:
                errores["puesto_eleccion"] = "El puesto debe pertenecer al mismo claustro que la lista."
            if self.puesto_eleccion.eleccion_claustro_departamento_id != self.eleccion_claustro_departamento_id:
                errores["puesto_eleccion"] = "El puesto debe tener el mismo alcance departamental que la lista."
            if self.participacion_id and self.puesto_eleccion.eleccion_claustro.eleccion_id != self.participacion.eleccion_id:
                errores["puesto_eleccion"] = "El puesto debe pertenecer a la elección de la presentación."
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        alcance = str(self.eleccion_claustro.claustro)
        if self.eleccion_claustro_departamento_id:
            alcance = f"{alcance} / {self.eleccion_claustro_departamento.departamento}"
        return f"{self.nombre} - {alcance}"


class Candidato(models.Model):
    class Tipo(models.TextChoices):
        TITULAR = "titular", "Titular"
        SUPLENTE = "suplente", "Suplente"

    lista = models.ForeignKey(ListaCandidatos, on_delete=models.PROTECT, related_name="candidatos")
    elector = models.ForeignKey(
        Elector,
        on_delete=models.PROTECT,
        related_name="candidaturas",
        null=True,
        blank=True,
        help_text="Vinculo opcional: un candidato no necesita integrar el padron.",
    )
    nombre = models.CharField(max_length=180, blank=True)
    identificador_persona = models.CharField(
        max_length=40,
        blank=True,
        help_text="Identificador consignado por la Junta; no se presume que sea DNI o legajo.",
    )
    dni = models.CharField("DNI", max_length=12, blank=True)
    correo_electronico = models.EmailField(blank=True)
    cargo = models.CharField(max_length=120)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.TITULAR)
    orden = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("cargo", "tipo", "orden", "nombre")
        constraints = [
            models.UniqueConstraint(
                fields=("lista", "dni"),
                condition=~models.Q(dni=""),
                name="dni_candidato_unico_por_lista",
            ),
            models.UniqueConstraint(
                fields=("lista", "identificador_persona"),
                condition=~models.Q(identificador_persona=""),
                name="identificador_unico_por_lista",
            ),
            models.UniqueConstraint(fields=("lista", "tipo", "orden"), name="orden_unico_por_lista_y_tipo"),
        ]

    def clean(self):
        errores = {}
        if self.elector_id:
            self.nombre = self.elector.nombre_completo
            self.dni = self.elector.dni
            if not self.correo_electronico:
                self.correo_electronico = self.elector.correo_electronico
        if self.lista_id and self.lista.puesto_eleccion_id:
            self.cargo = self.lista.puesto_eleccion.puesto.nombre
            limite = (
                self.lista.puesto_eleccion.cantidad_titulares
                if self.tipo == self.Tipo.TITULAR
                else self.lista.puesto_eleccion.cantidad_suplentes
            )
            if self.orden and self.orden > limite:
                errores["orden"] = f"El orden supera los {limite} puestos {self.tipo} configurados."
        if not self.nombre.strip():
            errores["nombre"] = "Debe indicar el nombre o seleccionar un elector existente."
        if not self.dni.strip() and not self.identificador_persona.strip():
            errores["identificador_persona"] = "Debe indicar un identificador de persona, un DNI o seleccionar un elector existente."

        if self.lista_id and self.dni:
            eleccion_id = self.lista.participacion.eleccion_id
            if self.elector_id:
                registro = self.elector.registros_padron.filter(eleccion_id=eleccion_id).select_related(
                    "eleccion_claustro_departamento",
                ).first()
                if registro:
                    configuracion = registro.eleccion_claustro_departamento
                    if configuracion.eleccion_claustro_id != self.lista.eleccion_claustro_id:
                        errores["elector"] = "El elector pertenece a otro claustro en el padron de esta eleccion."
                    elif self.lista.eleccion_claustro_departamento_id and configuracion.id != self.lista.eleccion_claustro_departamento_id:
                        errores["elector"] = "El elector pertenece a otro departamento en el padron de esta eleccion."
        if errores:
            raise ValidationError(errores)

    def __str__(self):
        return f"{self.nombre} - {self.cargo} ({self.get_tipo_display()} {self.orden})"


class ImportacionCandidaturas(models.Model):
    class Estado(models.TextChoices):
        PREVISUALIZADA = "previsualizada", "Previsualizada"
        CONFIRMADA = "confirmada", "Confirmada"
        RECHAZADA = "rechazada", "Rechazada"

    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="importaciones_candidaturas")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    nombre_archivo = models.CharField(max_length=255)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PREVISUALIZADA)
    filas = models.JSONField(default=list)
    errores = models.JSONField(default=list)
    advertencias = models.JSONField(default=list)
    cantidad_total = models.PositiveIntegerField(default=0)
    cantidad_valida = models.PositiveIntegerField(default=0)
    creada_en = models.DateTimeField(auto_now_add=True)
    confirmada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-creada_en",)
