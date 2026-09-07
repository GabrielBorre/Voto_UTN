from django.urls import path
from .views import (
    configurar_eleccion,
    cambiar_estado_eleccion,
    crear_eleccion,
    editar_alcance_sedes,
    editar_eleccion,
    gestionar_elecciones,
    gestionar_alcances,
    preparar_claustro,
    preparar_eleccion,
    historial_elecciones,
    listar_elecciones,
    index,
)

urlpatterns = [
    path("", index, name="index"),
    path("gestion/elecciones/listar_elecciones/", listar_elecciones, name="lista-elecciones"),
    path("gestion/elecciones/", gestionar_elecciones, name="gestionar-elecciones"),
    path("gestion/elecciones/historial/", historial_elecciones, name="historial-elecciones"),
    path("gestion/elecciones/nueva/", crear_eleccion, name="crear-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/", preparar_eleccion, name="preparar-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/", preparar_claustro, name="preparar-claustro"),
    path("gestion/elecciones/<int:eleccion_id>/editar/", editar_eleccion, name="editar-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/configuracion/", configurar_eleccion, name="configurar-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/estado/", cambiar_estado_eleccion, name="cambiar-estado-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/alcances/", gestionar_alcances, name="gestionar-alcances"),
    path("gestion/elecciones/<int:eleccion_id>/alcances/<str:tipo>/<int:objeto_id>/", editar_alcance_sedes, name="editar-alcance-sedes"),
]
