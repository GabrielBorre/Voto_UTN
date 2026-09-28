import re

from django.core.exceptions import ValidationError
from django.db import models

from apps.elecciones.models import Eleccion
from apps.parametros.models import Claustro, FechaAdministrativa


class PlantillaNotificacion(models.Model):
    class Categoria(models.TextChoices):
        CALENDARIO = "calendario", "Calendario administrativo"
        JORNADA = "jornada", "Jornada electoral"
        TRANSACCIONAL = "transaccional", "Resultado de tramite"
        MANUAL = "manual", "Envio manual"

    VARIABLES_PERMITIDAS = {
        "nombre_destinatario", "nombre_eleccion", "nombre_fecha_administrativa",
        "fecha_inicio", "fecha_fin", "claustros", "mesa", "sede", "turno",
        "horario_turno", "fecha_votacion", "url_accion", "fecha_capacitacion",
        "hora_capacitacion", "lugar_capacitacion", "fecha_presentacion",
        "estado_solicitud", "observacion_resolucion", "sede_solicitada",
        "turno_solicitado",
    }

    codigo = models.SlugField(max_length=100, unique=True)
    nombre = models.CharField(max_length=160, unique=True)
    categoria = models.CharField(max_length=20, choices=Categoria.choices, default=Categoria.MANUAL)
    descripcion = models.TextField(blank=True)
    asunto = models.CharField(max_length=180)
    contenido = models.TextField()
    roles_destinatarios = models.JSONField(default=list)
    claustros = models.ManyToManyField(
        Claustro,
        related_name="plantillas_notificacion",
        blank=True,
        db_table="elecciones_plantillanotificacion_claustros",
    )
    permite_envio_manual = models.BooleanField(default=True)
    activa = models.BooleanField(default=True)

    class Meta:
        db_table = "elecciones_plantillanotificacion"
        ordering = ("nombre",)

    def clean(self):
        roles_validos = {rol for rol, _ in FechaAdministrativa.RolDestinatario.choices}
        if not self.roles_destinatarios:
            raise ValidationError({"roles_destinatarios": "Debe seleccionar al menos un rol destinatario."})
        if not set(self.roles_destinatarios).issubset(roles_validos):
            raise ValidationError({"roles_destinatarios": "Contiene roles destinatarios invalidos."})
        variables = set(re.findall(r"\{([a-zA-Z0-9_]+)\}", f"{self.asunto}\n{self.contenido}"))
        desconocidas = sorted(variables - self.VARIABLES_PERMITIDAS)
        if desconocidas:
            raise ValidationError(
                {"contenido": f"Variables no permitidas: {', '.join('{' + item + '}' for item in desconocidas)}."}
            )

    @property
    def roles_destinatarios_display(self):
        etiquetas = dict(FechaAdministrativa.RolDestinatario.choices)
        return ", ".join(etiquetas[rol] for rol in self.roles_destinatarios if rol in etiquetas)

    def __str__(self):
        return self.nombre


class ComunicacionFechaAdministrativa(models.Model):
    class Referencia(models.TextChoices):
        INICIO = "inicio", "Inicio"
        FIN = "fin", "Fin"

    fecha_administrativa = models.ForeignKey(
        FechaAdministrativa,
        on_delete=models.CASCADE,
        related_name="comunicaciones",
    )
    codigo = models.SlugField(max_length=80)
    nombre = models.CharField(max_length=160)
    referencia = models.CharField(max_length=10, choices=Referencia.choices, default=Referencia.INICIO)
    desplazamiento_dias = models.SmallIntegerField(default=0)
    hora_sugerida = models.TimeField(default="09:00")
    orden = models.PositiveSmallIntegerField(default=1)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("orden", "id")
        constraints = [
            models.UniqueConstraint(fields=("fecha_administrativa", "codigo"), name="uniq_comunicacion_fecha_codigo")
        ]

    def __str__(self):
        return f"{self.fecha_administrativa}: {self.nombre}"


class VarianteComunicacionFechaAdministrativa(models.Model):
    class CriterioAdicional(models.TextChoices):
        NINGUNO = "", "Sin filtro adicional"
        HABILITADO_CAMBIO_SEDE = "habilitado_cambio_sede", "Habilitado para cambio de sede"
        SIN_SOLICITUD_PRESENTADA = "sin_solicitud_presentada", "Sin solicitud presentada"
        AUTORIDAD_VIGENTE_SIN_SOLICITUD = "autoridad_vigente_sin_solicitud", "Autoridad vigente sin solicitud"

    comunicacion = models.ForeignKey(
        ComunicacionFechaAdministrativa,
        on_delete=models.CASCADE,
        related_name="variantes",
    )
    plantilla = models.ForeignKey(
        PlantillaNotificacion,
        on_delete=models.PROTECT,
        related_name="variantes_calendario",
    )
    criterio_adicional = models.CharField(
        max_length=50,
        choices=CriterioAdicional.choices,
        blank=True,
        default="",
    )
    prioridad = models.PositiveSmallIntegerField(default=1)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("prioridad", "id")
        constraints = [
            models.UniqueConstraint(fields=("comunicacion", "prioridad"), name="uniq_variante_comunicacion_prioridad")
        ]

    def clean(self):
        if self.plantilla_id and self.comunicacion_id and not set(self.plantilla.roles_destinatarios).issubset(
            set(self.comunicacion.fecha_administrativa.roles_destinatarios)
        ):
            raise ValidationError({"plantilla": "La variante no puede ampliar los roles definidos por la fecha."})


class EnvioNotificacion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADO = "enviado", "Enviado"
        ERROR = "error", "Error"

    plantilla = models.ForeignKey(PlantillaNotificacion, on_delete=models.PROTECT, related_name="envios")
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="envios_notificacion", null=True, blank=True)
    destinatario = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="notificaciones")
    asunto = models.CharField(max_length=180)
    contenido = models.TextField()
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    creada_en = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)
    leida_en = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "elecciones_envionotificacion"
        ordering = ("-creada_en",)
