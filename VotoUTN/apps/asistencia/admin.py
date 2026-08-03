from django.contrib import admin
from .models import Asistencia

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ("codigo_elector", "eleccion", "registrada_por", "registrada_en")
    list_filter = ("eleccion",)
    search_fields = ("codigo_elector",)
    readonly_fields = ("registrada_en",)
