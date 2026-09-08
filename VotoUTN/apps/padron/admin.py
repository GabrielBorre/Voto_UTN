from django.contrib import admin

from apps.padron.models import Elector, ErrorImportacionPadron, ImportacionPadron, RegistroPadron


@admin.register(Elector)
class ElectorAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "nombre", "dni")
    search_fields = ("legajo", "nombre", "dni")


admin.site.register((RegistroPadron, ImportacionPadron, ErrorImportacionPadron))
