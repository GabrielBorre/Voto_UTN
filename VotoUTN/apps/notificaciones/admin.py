from django.contrib import admin

from apps.notificaciones.models import (
    ComunicacionFechaAdministrativa,
    EnvioNotificacion,
    PlantillaNotificacion,
    VarianteComunicacionFechaAdministrativa,
)


@admin.register(PlantillaNotificacion)
class PlantillaNotificacionAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register((ComunicacionFechaAdministrativa, VarianteComunicacionFechaAdministrativa, EnvioNotificacion))
