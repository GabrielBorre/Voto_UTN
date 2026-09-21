from django.contrib import admin

from apps.justificativos.models import JustificativoAusencia, TipoJustificativo


@admin.register(TipoJustificativo)
class TipoJustificativoAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(JustificativoAusencia)
