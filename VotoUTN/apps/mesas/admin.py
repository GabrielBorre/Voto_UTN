from django.contrib import admin

from apps.mesas.models import AsignacionMesa, Mesa


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("id", "eleccion", "numero", "sede")
    list_filter = ("eleccion", "sede")
    search_fields = ("numero", "eleccion__nombre")


admin.site.register(AsignacionMesa)
