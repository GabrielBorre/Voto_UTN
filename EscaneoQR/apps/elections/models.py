from django.db import models


class Election(models.Model):
    name = models.CharField("nombre", max_length=180)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    is_active = models.BooleanField("habilitada", default=True)

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return self.name


class Voter(models.Model):
    legajo = models.CharField("legajo", max_length=20, unique=True)
    name = models.CharField("nombre", max_length=180)
    dni = models.CharField("DNI", max_length=12, unique=True)

    class Meta:
        ordering = ["legajo"]
        verbose_name = "elector"
        verbose_name_plural = "electores"

    def __str__(self):
        return f"{self.legajo} — {self.name}"
