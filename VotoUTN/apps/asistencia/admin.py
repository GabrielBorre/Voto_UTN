from django.contrib import admin
from .models import Asistencia

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = ("voter_code", "eleccion", "scanned_by", "scanned_at")
    list_filter = ("eleccion",)
    search_fields = ("voter_code",)
    readonly_fields = ("scanned_at",)
