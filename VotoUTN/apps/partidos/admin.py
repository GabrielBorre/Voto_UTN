from django.contrib import admin

from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido, Partido


@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sigla", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "sigla")


@admin.register(ParticipacionPartido)
class ParticipacionPartidoAdmin(admin.ModelAdmin):
    list_display = ("partido", "eleccion", "numero_lista", "activa")
    list_filter = ("eleccion", "activa")
    search_fields = ("partido__nombre", "numero_lista", "nombre_lista")


@admin.register(ListaCandidatos)
class ListaCandidatosAdmin(admin.ModelAdmin):
    list_display = ("nombre", "participacion", "eleccion_claustro", "activa")
    list_filter = ("activa", "participacion__eleccion")
    search_fields = ("nombre", "participacion__partido__nombre")


@admin.register(Candidato)
class CandidatoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "dni", "lista", "cargo", "tipo", "orden", "activo")
    list_filter = ("activo", "tipo", "lista__participacion__eleccion")
    search_fields = ("nombre", "dni", "lista__participacion__partido__nombre")
