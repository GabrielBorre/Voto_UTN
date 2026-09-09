from django.contrib import admin

from apps.justificativos.models import JustificativoAusencia, TipoJustificativo


admin.site.register((TipoJustificativo, JustificativoAusencia))
