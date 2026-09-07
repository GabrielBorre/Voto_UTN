from django.contrib import admin

from .models import EventoAuditoria


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "accion", "entidad", "entidad_id", "eleccion", "usuario")
    list_filter = ("accion", "entidad", "creado_en")
    search_fields = ("accion", "entidad", "entidad_id", "usuario__username")
    readonly_fields = (
        "accion",
        "entidad",
        "entidad_id",
        "eleccion",
        "usuario",
        "datos_anteriores",
        "datos_nuevos",
        "ip",
        "agente_usuario",
        "creado_en",
    )
