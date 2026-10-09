from django.contrib import admin

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


admin.site.register((
    RegistroPadron,
    ImportacionPadron,
    ErrorImportacionPadron,
    ConfiguracionSedesClaustro,
    ReglaSedeClaustro,
    AsignacionSedePadron,
))
