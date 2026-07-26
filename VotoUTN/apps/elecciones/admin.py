from django.contrib import admin
from .models import Eleccion, Votante

@admin.register(Eleccion)
class EleccionAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_at", "ends_at", "is_active")
    list_filter = ("is_active",)


@admin.register(Votante)
class VotanteAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "name", "dni")
    search_fields = ("legajo", "name", "dni")
    ordering = ("legajo",)
