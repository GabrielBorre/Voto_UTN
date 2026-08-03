from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.elecciones.models import Eleccion, Elector, Mesa, Sede


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_electoral")
    elector = models.OneToOneField(Elector, on_delete=models.PROTECT, related_name="perfil_usuario", null=True, blank=True)
    activo = models.BooleanField(default=True)


class AsignacionRol(models.Model):
    class Rol(models.TextChoices):
        ADMINISTRADOR_SISTEMA = "administrador_sistema", "Administrador del sistema"
        ADMINISTRADOR_JUNTA = "administrador_junta", "Administrador de junta"
        ADMINISTRATIVO_JUNTA = "administrativo_junta", "Administrativo de junta"
        AUTORIDAD_MESA = "autoridad_mesa", "Autoridad de mesa"
        ELECTOR = "elector", "Elector"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="asignaciones_rol")
    rol = models.CharField(max_length=32, choices=Rol.choices)
    eleccion = models.ForeignKey(Eleccion, on_delete=models.PROTECT, related_name="asignaciones_rol", null=True, blank=True)
    sede = models.ForeignKey(Sede, on_delete=models.PROTECT, related_name="asignaciones_rol", null=True, blank=True)
    mesa = models.ForeignKey(Mesa, on_delete=models.PROTECT, related_name="asignaciones_rol", null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("usuario", "rol", "eleccion", "sede", "mesa"), name="rol_unico_por_alcance")]

    def clean(self):
        if self.rol == self.Rol.ADMINISTRADOR_SISTEMA:
            if self.eleccion_id or self.sede_id or self.mesa_id:
                raise ValidationError("El administrador del sistema no admite alcance electoral.")
            return
        if not self.eleccion_id:
            raise ValidationError({"eleccion": "El rol requiere una elección."})
        if self.mesa_id and self.mesa.eleccion_id != self.eleccion_id:
            raise ValidationError({"mesa": "Debe pertenecer a la elección asignada."})
        if self.sede_id and not self.eleccion.elecciones_sede.filter(sede=self.sede).exists():
            raise ValidationError({"sede": "Debe estar habilitada para la elección."})
        if self.mesa_id and self.sede_id and self.mesa.sede_id != self.sede_id:
            raise ValidationError({"mesa": "Debe pertenecer a la sede asignada."})
        if self.rol == self.Rol.AUTORIDAD_MESA:
            perfil = getattr(self.usuario, "perfil_electoral", None)
            if perfil is None or perfil.elector_id is None:
                raise ValidationError({"usuario": "La autoridad debe estar vinculada a un elector."})
