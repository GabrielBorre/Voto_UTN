from django.contrib import admin

from apps.elecciones.admin_permissions import EleccionCerradaAdminMixin
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


for modelo in (
    EleccionSede,
    EleccionClaustro,
    EleccionClaustroSede,
    EleccionClaustroTurno,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    FechaAdministrativaEleccion,
):
    admin.site.register(modelo, EleccionCerradaAdminMixin)


@admin.register(Eleccion)
class EleccionAdmin(EleccionCerradaAdminMixin):
    list_display = ("nombre", "estado", "fecha_inicio", "fecha_fin", "habilitada")
    list_filter = ("estado", "habilitada")
