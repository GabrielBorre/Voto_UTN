from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
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


class ParticipacionPartido(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="partidos_participantes")
    partido = models.ForeignKey(Partido, on_delete=models.PROTECT, related_name="participaciones")
    numero_lista = models.CharField(max_length=20)
    nombre_lista = models.CharField(max_length=180, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("numero_lista", "partido__nombre")
        constraints = [
            models.UniqueConstraint(fields=("eleccion", "partido"), name="partido_unico_por_eleccion"),
            models.UniqueConstraint(fields=("eleccion", "numero_lista"), name="numero_lista_unico_por_eleccion"),
        ]

    def __str__(self):
        return f"Lista {self.numero_lista} - {self.partido}"


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
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("eleccion_claustro__claustro__nombre", "nombre")
        constraints = [
            models.UniqueConstraint(
                fields=("participacion", "eleccion_claustro"),
                condition=models.Q(eleccion_claustro_departamento__isnull=True),
                name="lista_unica_por_partido_y_claustro",
            ),
            models.UniqueConstraint(
                fields=("participacion", "eleccion_claustro_departamento"),
                condition=models.Q(eleccion_claustro_departamento__isnull=False),
                name="lista_unica_por_partido_y_departamento",
            ),
        ]

    def clean(self):
        errores = {}
        if self.participacion_id and self.eleccion_claustro_id:
            if self.participacion.eleccion_id != self.eleccion_claustro.eleccion_id:
                errores["eleccion_claustro"] = "El claustro debe pertenecer a la eleccion del partido."
        if self.eleccion_claustro_departamento_id and self.eleccion_claustro_id:
            if self.eleccion_claustro_departamento.eleccion_claustro_id != self.eleccion_claustro_id:
                errores["eleccion_claustro_departamento"] = "El departamento debe pertenecer al claustro seleccionado."
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
    dni = models.CharField("DNI", max_length=12, blank=True)
    correo_electronico = models.EmailField(blank=True)
    cargo = models.CharField(max_length=120)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.TITULAR)
    orden = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("cargo", "tipo", "orden", "nombre")
        constraints = [
            models.UniqueConstraint(fields=("lista", "dni"), name="candidato_unico_por_lista"),
            models.UniqueConstraint(fields=("lista", "cargo", "tipo", "orden"), name="orden_unico_por_lista_y_cargo"),
        ]

    def clean(self):
        errores = {}
        if self.elector_id:
            self.nombre = self.elector.nombre
            self.dni = self.elector.dni
            if not self.correo_electronico:
                self.correo_electronico = self.elector.correo_electronico
        if not self.nombre.strip():
            errores["nombre"] = "Debe indicar el nombre o seleccionar un elector existente."
        if not self.dni.strip():
            errores["dni"] = "Debe indicar el DNI o seleccionar un elector existente."

        if self.lista_id and self.dni:
            eleccion_id = self.lista.participacion.eleccion_id
            if Candidato.objects.filter(lista__participacion__eleccion_id=eleccion_id, dni=self.dni).exclude(pk=self.pk).exists():
                errores["dni"] = "La persona ya integra una lista de esta eleccion."

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
