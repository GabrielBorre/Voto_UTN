import secrets
import string

from django.core.exceptions import ValidationError
from django.db import models

from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.parametros.models import Sede


class Elector(models.Model):
    legajo = models.CharField("legajo", max_length=20, unique=True)
    nombre = models.CharField("nombre", max_length=180)
    dni = models.CharField("DNI", max_length=12, unique=True)
    correo_electronico = models.EmailField("correo electronico", blank=True)

    class Meta:
        db_table = "elecciones_elector"
        ordering = ["legajo"]

    def __str__(self):
        return f"{self.legajo} - {self.nombre}"


class RegistroPadron(models.Model):
    ALFABETO_CODIGO_QR = string.ascii_uppercase + string.digits
    LONGITUD_CODIGO_QR = 8

    elector = models.ForeignKey(Elector, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="registros_padron")
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="registros_padron", null=True, blank=True)
    activo = models.BooleanField(default=True)
    identificador_qr = models.CharField(max_length=LONGITUD_CODIGO_QR, unique=True, blank=True, editable=False)

    class Meta:
        db_table = "elecciones_registropadron"
        constraints = [models.UniqueConstraint(fields=("elector", "eleccion"), name="elector_unico_por_eleccion")]

    def clean(self):
        self.validar_sede()
        if self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma eleccion."})

    def validar_sede(self):
        if self.sede_id and not EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento=self.eleccion_claustro_departamento,
            sede=self.sede,
        ).exists():
            raise ValidationError({"sede": "Debe estar habilitada para el departamento del padron."})

    @classmethod
    def generar_codigo_qr_corto(cls):
        return "".join(secrets.choice(cls.ALFABETO_CODIGO_QR) for _ in range(cls.LONGITUD_CODIGO_QR))

    def save(self, *args, **kwargs):
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
