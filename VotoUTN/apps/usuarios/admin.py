from django.contrib import admin

from .models import AsignacionRol, PerfilUsuario


admin.site.register((PerfilUsuario, AsignacionRol))
