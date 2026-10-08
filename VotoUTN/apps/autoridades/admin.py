from django.contrib import admin

from apps.elecciones.admin_permissions import EleccionCerradaAdminMixin
from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad


for modelo in (CandidaturaAutoridad, AsignacionAutoridad, PreferenciaAutoridad):
    admin.site.register(modelo, EleccionCerradaAdminMixin)
