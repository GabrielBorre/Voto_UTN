from django.contrib import admin

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad


admin.site.register((CandidaturaAutoridad, AsignacionAutoridad, PreferenciaAutoridad))
