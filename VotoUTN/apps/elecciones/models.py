from django.db import models


class Eleccion(models.Model):
    name = models.CharField("nombre", max_length=180)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    is_active = models.BooleanField("habilitada", default=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.name


class Mesa(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="mesas")
    numero = models.IntegerField("numero")

    class Meta:
        ordering = ["eleccion_id", "numero"]
        verbose_name = "mesa"
        verbose_name_plural = "mesas"
        constraints = [
            models.UniqueConstraint(fields=("eleccion", "numero"), name="unique_mesa_per_eleccion")
        ]

    def __str__(self):
        return f"{self.eleccion} - Mesa {self.numero}"


class Votante(models.Model):
    legajo = models.CharField("legajo", max_length=20, unique=True)
    name = models.CharField("nombre", max_length=180)
    dni = models.CharField("DNI", max_length=12, unique=True)
    mesa = models.ForeignKey(
        Mesa,
        on_delete=models.PROTECT,
        related_name="votantes",
        verbose_name="mesa",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["legajo"]
        verbose_name = "elector"
        verbose_name_plural = "electores"

    def __str__(self):
        return f"{self.legajo} — {self.name}"
