from django.contrib import admin

from .models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionClaustroTurno,
    EleccionSede,
    FechaAdministrativaEleccion,
)


admin.site.register((EleccionSede, EleccionClaustro, EleccionClaustroSede, EleccionClaustroTurno))
admin.site.register((EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, FechaAdministrativaEleccion))


@admin.register(Eleccion)
class EleccionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "estado", "fecha_inicio", "fecha_fin", "habilitada")
    list_filter = ("estado", "habilitada")
