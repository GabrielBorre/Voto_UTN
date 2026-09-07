from django.contrib import admin

from apps.elecciones.models import AsignacionMesa, Mesa


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("id", "eleccion", "numero", "sede", "turno")
    list_filter = ("eleccion", "sede", "turno")
    search_fields = ("numero", "eleccion__nombre")


admin.site.register(AsignacionMesa)
