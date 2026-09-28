from django.contrib import admin

from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ImportacionCandidaturas,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    Partido,
    PuestoEleccion,
)


@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sigla", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "sigla")


@admin.register(OrganoElectivo)
class OrganoElectivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)


@admin.register(CargoElectivo)
class CargoElectivoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "organo",
        "permite_filtrar_claustros",
        "permite_filtrar_departamentos",
        "activo",
    )
    list_filter = ("organo", "activo")
    search_fields = ("nombre", "organo__nombre")


@admin.register(ParticipacionPartido)
class ParticipacionPartidoAdmin(admin.ModelAdmin):
    list_display = ("codigo_presentacion", "numero_lista", "nombre_lista", "eleccion", "eleccion_claustro", "activa")
    list_filter = ("eleccion", "activa")
    search_fields = ("codigo_presentacion", "partido__nombre", "numero_lista", "nombre_lista", "apoderado_nombre")


@admin.register(PuestoEleccion)
class PuestoEleccionAdmin(admin.ModelAdmin):
    list_display = ("puesto", "eleccion_claustro", "eleccion_claustro_departamento", "cantidad_titulares", "cantidad_suplentes", "activo")
    list_filter = ("activo", "puesto__organo")


@admin.register(ImportacionCandidaturas)
class ImportacionCandidaturasAdmin(admin.ModelAdmin):
    list_display = ("nombre_archivo", "eleccion", "estado", "cantidad_total", "cantidad_valida", "creada_en")
    list_filter = ("estado", "eleccion")
    readonly_fields = ("filas", "errores", "advertencias", "creada_en", "confirmada_en")


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
