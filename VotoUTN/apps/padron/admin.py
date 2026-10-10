from django.contrib import admin

from apps.elecciones.admin_permissions import EleccionCerradaAdminMixin
from apps.padron.models import Elector, ErrorImportacionPadron, ImportacionPadron, RegistroPadron


@admin.register(Elector)
class ElectorAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "nombre", "apellido", "dni")
    search_fields = ("legajo", "nombre", "apellido", "dni")


for modelo in (RegistroPadron, ImportacionPadron, ErrorImportacionPadron):
    admin.site.register(modelo, EleccionCerradaAdminMixin)
