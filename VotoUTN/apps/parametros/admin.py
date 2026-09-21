from django.contrib import admin

from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


class ParametroSinBajaAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


for modelo in (Sede, Claustro, Turno, Departamento, FechaAdministrativa):
    admin.site.register(modelo, ParametroSinBajaAdmin)
