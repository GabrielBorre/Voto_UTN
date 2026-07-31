from django.contrib import admin
from .models import Eleccion, Mesa, Votante

@admin.register(Eleccion)
class EleccionAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_at", "ends_at", "is_active")
    list_filter = ("is_active",)


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("id", "eleccion", "numero")
    list_filter = ("eleccion",)
    search_fields = ("numero", "eleccion__name")
    ordering = ("eleccion", "numero")


@admin.register(Votante)
class VotanteAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "name", "dni", "mesa")
    list_filter = ("mesa", "mesa__eleccion")
    search_fields = ("legajo", "name", "dni", "mesa__numero", "mesa__eleccion__name")
    ordering = ("legajo",)
