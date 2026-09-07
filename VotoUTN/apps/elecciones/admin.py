from django.contrib import admin

from .models import (
    Claustro,
    Departamento,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    EleccionTurno,
    Elector,
    FechaAdministrativa,
    FechaAdministrativaEleccion,
    RegistroPadron,
    Sede,
    Turno,
)


admin.site.register((Sede, Claustro, Turno, Departamento, FechaAdministrativa, EleccionSede, EleccionClaustro, EleccionClaustroSede, EleccionTurno))
admin.site.register((EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, FechaAdministrativaEleccion, RegistroPadron))


@admin.register(Eleccion)
class EleccionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "estado", "fecha_inicio", "fecha_fin", "habilitada")
    list_filter = ("estado", "habilitada")


@admin.register(Elector)
class ElectorAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "nombre", "dni")
    search_fields = ("legajo", "nombre", "dni")
