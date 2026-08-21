from django.contrib import admin
from .models import RegistroParticipacion

@admin.register(RegistroParticipacion)
class RegistroParticipacionAdmin(admin.ModelAdmin):
    list_display = ("registro_padron", "mesa", "metodo", "registrada_por", "registrada_en")
    list_filter = ("metodo", "mesa", "registro_padron__eleccion")
    search_fields = ("registro_padron__elector__legajo", "registro_padron__elector__dni", "mesa__numero")
    readonly_fields = ("registrada_en",)
