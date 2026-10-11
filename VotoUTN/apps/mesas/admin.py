from django.contrib import admin

from apps.elecciones.admin_permissions import EleccionCerradaAdminMixin
from apps.mesas.models import AsignacionMesa, Mesa


@admin.register(Mesa)
class MesaAdmin(EleccionCerradaAdminMixin):
    list_display = ("id", "eleccion", "numero", "sede")
    list_filter = ("eleccion", "sede")
    search_fields = ("numero", "eleccion__nombre")


admin.site.register(AsignacionMesa, EleccionCerradaAdminMixin)
