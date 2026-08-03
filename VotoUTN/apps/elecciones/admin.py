from django.contrib import admin

from .models import (
    AsignacionMesa,
    Claustro,
    Departamento,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    Elector,
    Mesa,
    RegistroPadron,
    Sede,
    Turno,
)


admin.site.register((Sede, Claustro, Turno, Departamento, EleccionSede, EleccionClaustro, EleccionClaustroSede))
admin.site.register((EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede, RegistroPadron, AsignacionMesa))


@admin.register(Eleccion)
class EleccionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha_inicio", "fecha_fin", "habilitada")
    list_filter = ("habilitada",)


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("id", "eleccion", "numero", "sede", "turno")
    list_filter = ("eleccion", "sede", "turno")
    search_fields = ("numero", "eleccion__nombre")


@admin.register(Elector)
class ElectorAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "nombre", "dni", "mesa")
    list_filter = ("mesa", "mesa__eleccion")
    search_fields = ("legajo", "nombre", "dni", "mesa__numero", "mesa__eleccion__nombre")
