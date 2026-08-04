import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Sede(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Claustro(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Turno(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("hora_inicio", "nombre")

    def clean(self):
        if self.hora_inicio >= self.hora_fin:
            raise ValidationError({"hora_fin": "Debe ser posterior a la hora de inicio."})

    def __str__(self):
        return self.nombre


class Departamento(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    codigo = models.CharField(max_length=20, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class FechaAdministrativa(models.Model):
    class RolDestinatario(models.TextChoices):
        ADMINISTRADOR_JUNTA = "administrador_junta", "Administrador de junta"
        ADMINISTRATIVO_JUNTA = "administrativo_junta", "Administrativo de junta"
        AUTORIDAD_MESA = "autoridad_mesa", "Autoridad de mesa"
        ELECTOR = "elector", "Elector"

    nombre = models.CharField(max_length=160, unique=True)
    roles_destinatarios = models.JSONField(default=list)
    claustros = models.ManyToManyField(Claustro, related_name="fechas_administrativas")
    asunto_notificacion = models.CharField(max_length=180)
    mensaje_notificacion = models.TextField()
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def clean(self):
        roles_validos = {rol for rol, _ in self.RolDestinatario.choices}
        if not self.roles_destinatarios:
            raise ValidationError({"roles_destinatarios": "Debe seleccionar al menos un rol destinatario."})
        if not set(self.roles_destinatarios).issubset(roles_validos):
            raise ValidationError({"roles_destinatarios": "Contiene roles destinatarios invalidos."})

    @property
    def roles_destinatarios_display(self):
        etiquetas = dict(self.RolDestinatario.choices)
        return ", ".join(etiquetas[rol] for rol in self.roles_destinatarios)

    def __str__(self):
        return self.nombre


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
            raise ValidationError({"sede": "La sede debe estar habilitada para la elección."})


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


class Mesa(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="mesas")
    numero = models.PositiveIntegerField("numero")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="mesas", null=True, blank=True)
    generada_automaticamente = models.BooleanField(default=False)

    class Meta:
        ordering = ["eleccion_id", "numero"]
        constraints = [models.UniqueConstraint(fields=("eleccion", "numero"), name="unique_mesa_per_eleccion")]

    def clean(self):
        if self.eleccion_claustro_departamento_id and self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma elección."})
        if self.eleccion_claustro_departamento_id and self.sede_id and not EleccionClaustroDepartamentoSede.objects.filter(eleccion_claustro_departamento=self.eleccion_claustro_departamento, sede=self.sede).exists():
            raise ValidationError({"sede": "La sede debe estar habilitada para el departamento."})
        if self.eleccion_id and self.turno_id and not EleccionTurno.objects.filter(eleccion_id=self.eleccion_id, turno_id=self.turno_id).exists():
            raise ValidationError({"turno": "El turno debe estar habilitado para la eleccion."})

    def __str__(self):
        return f"{self.eleccion} - Mesa {self.numero}"


class Elector(models.Model):
    legajo = models.CharField("legajo", max_length=20, unique=True)
    nombre = models.CharField("nombre", max_length=180)
    dni = models.CharField("DNI", max_length=12, unique=True)
    correo_electronico = models.EmailField("correo electronico", blank=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="electores", null=True, blank=True)

    class Meta:
        ordering = ["legajo"]

    def __str__(self):
        return f"{self.legajo} - {self.nombre}"


class RegistroPadron(models.Model):
    elector = models.ForeignKey(Elector, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="registros_padron")
    eleccion_claustro_departamento = models.ForeignKey(EleccionClaustroDepartamento, on_delete=models.PROTECT, related_name="registros_padron")
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="registros_padron", null=True, blank=True)
    activo = models.BooleanField(default=True)
    identificador_qr = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("elector", "eleccion"), name="elector_unico_por_eleccion")]

    def clean(self):
        self.validar_sede()
        if self.eleccion_id != self.eleccion_claustro_departamento.eleccion_claustro.eleccion_id:
            raise ValidationError({"eleccion_claustro_departamento": "Debe pertenecer a la misma elección."})


    def validar_sede(self):
        if self.sede_id and not EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento=self.eleccion_claustro_departamento,
            sede=self.sede,
        ).exists():
            raise ValidationError({"sede": "Debe estar habilitada para el departamento del padron."})


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
        ordering = ("fila", "id")


class PlantillaNotificacion(models.Model):
    nombre = models.CharField(max_length=160, unique=True)
    asunto = models.CharField(max_length=180)
    contenido = models.TextField()
    roles_destinatarios = models.JSONField(default=list)
    claustros = models.ManyToManyField(Claustro, related_name="plantillas_notificacion", blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)


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
        ordering = ("-creada_en",)


class FechaAdministrativaEleccion(models.Model):
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="fechas_administrativas")
    fecha_administrativa = models.ForeignKey(FechaAdministrativa, on_delete=models.PROTECT, related_name="programaciones")
    fecha = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("eleccion", "fecha_administrativa"), name="fecha_administrativa_unica_por_eleccion")]

    def clean(self):
        if self.eleccion_id and self.fecha and not self.eleccion.fecha_inicio.date() <= self.fecha <= self.eleccion.fecha_fin.date():
            raise ValidationError({"fecha": "Debe estar comprendida entre el inicio y el fin de la eleccion."})


class CandidaturaAutoridad(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="candidatura_autoridad")
    cargada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="candidaturas_autoridad_cargadas")
    cargada_en = models.DateTimeField(auto_now_add=True)


class AsignacionAutoridad(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADA = "confirmada", "Confirmada"
        RECHAZADA = "rechazada", "Rechazada"

    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="asignacion_autoridad")
    candidatura = models.OneToOneField(CandidaturaAutoridad, on_delete=models.PROTECT, related_name="asignacion", null=True, blank=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="autoridades")
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    asignada_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, related_name="autoridades_asignadas")
    asignada_en = models.DateTimeField(auto_now_add=True)
    respondida_en = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.registro_padron_id and self.mesa_id:
            if self.candidatura_id and self.candidatura.registro_padron_id != self.registro_padron_id:
                raise ValidationError({"candidatura": "Debe corresponder al mismo elector del padron."})
            if self.registro_padron.eleccion_id != self.mesa.eleccion_id:
                raise ValidationError({"mesa": "Debe pertenecer a la misma eleccion que el padron."})
            if self.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id != self.mesa.eleccion_claustro_departamento.eleccion_claustro_id:
                raise ValidationError({"mesa": "La autoridad debe pertenecer al mismo claustro que la mesa."})


class PreferenciaAutoridad(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="preferencia_autoridad")
    sede_preferida = models.ForeignKey(Sede, on_delete=models.PROTECT, null=True, blank=True, related_name="preferencias_autoridad")
    turno_preferido = models.ForeignKey(Turno, on_delete=models.PROTECT, null=True, blank=True, related_name="preferencias_autoridad")
    disponible = models.BooleanField(default=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.registro_padron_id and self.sede_preferida_id and self.sede_preferida_id != self.registro_padron.sede_id:
            raise ValidationError({"sede_preferida": "La sede preferida debe ser la sede del padron."})


class TipoJustificativo(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class JustificativoAusencia(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        APROBADO = "aprobado", "Aprobado"
        RECHAZADO = "rechazado", "Rechazado"

    registro_padron = models.ForeignKey(RegistroPadron, on_delete=models.PROTECT, related_name="justificativos")
    tipo = models.ForeignKey(TipoJustificativo, on_delete=models.PROTECT, related_name="justificativos")
    detalle = models.TextField()
    documento = models.FileField(upload_to="justificativos/%Y/%m/%d", blank=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PENDIENTE)
    presentada_en = models.DateTimeField(auto_now_add=True)
    resuelta_por = models.ForeignKey("auth.User", on_delete=models.PROTECT, null=True, blank=True, related_name="justificativos_resueltos")
    resuelta_en = models.DateTimeField(null=True, blank=True)
    observacion_resolucion = models.TextField(blank=True)

    def clean(self):
        if self.resuelta_por_id and self.estado == self.Estado.PENDIENTE:
            raise ValidationError({"estado": "Un justificativo resuelto debe estar aprobado o rechazado."})


class AsignacionMesa(models.Model):
    registro_padron = models.OneToOneField(RegistroPadron, on_delete=models.PROTECT, related_name="asignacion_mesa")
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="asignaciones_padron")

    def clean(self):
        if self.registro_padron_id and self.mesa_id and self.registro_padron.eleccion_id != self.mesa.eleccion_id:
            raise ValidationError({"mesa": "Debe pertenecer a la misma elección del padrón."})
