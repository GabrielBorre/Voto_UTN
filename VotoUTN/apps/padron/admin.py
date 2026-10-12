from django.contrib import admin

from apps.elecciones.admin_permissions import EleccionCerradaAdminMixin
from apps.padron.models import (
    AsignacionSedePadron,
    ConfiguracionSedesClaustro,
    Elector,
    ErrorImportacionPadron,
    ImportacionPadron,
    RegistroPadron,
    ReglaSedeClaustro,
)


@admin.register(Elector)
class ElectorAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "nombre", "apellido", "dni")
    search_fields = ("legajo", "nombre", "apellido", "dni")


for modelo in (
    RegistroPadron,
    ImportacionPadron,
    ErrorImportacionPadron,
    ConfiguracionSedesClaustro,
    ReglaSedeClaustro,
    AsignacionSedePadron,
):
    admin.site.register(modelo, EleccionCerradaAdminMixin)
