from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import AsignacionRol, PerfilUsuario


class PerfilUsuarioInline(admin.StackedInline):
	model = PerfilUsuario
	extra = 0
	max_num = 1


class AsignacionRolInline(admin.TabularInline):
	model = AsignacionRol
	extra = 0


class UsuarioInternoAdmin(UserAdmin):
	inlines = (PerfilUsuarioInline, AsignacionRolInline)


admin.site.unregister(User)
admin.site.register(User, UsuarioInternoAdmin)


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
	list_display = ("usuario", "dni", "elector", "activo")
	search_fields = ("dni", "usuario__username", "usuario__email")
	list_filter = ("activo",)


@admin.register(AsignacionRol)
class AsignacionRolAdmin(admin.ModelAdmin):
	list_display = ("usuario", "rol", "eleccion", "sede", "mesa", "activo")
	list_filter = ("rol", "activo")
	search_fields = ("usuario__username", "usuario__email")
