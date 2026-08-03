from django.urls import path
from .views import (
    cambiar_estado_parametro,
    crear_eleccion,
    editar_parametro,
    gestionar_elecciones,
    gestionar_mesas,
    gestionar_parametros,
    listar_elecciones,
    listar_parametros,
)

urlpatterns = [
    path("", listar_elecciones, name="lista-elecciones"),
    path("gestion/elecciones/", gestionar_elecciones, name="gestionar-elecciones"),
    path("gestion/elecciones/nueva/", crear_eleccion, name="crear-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/mesas/", gestionar_mesas, name="gestionar-mesas"),
    path("gestion/parametros/", gestionar_parametros, name="gestionar-parametros"),
    path("gestion/parametros/<str:tipo>/", listar_parametros, name="listar-parametros"),
    path("gestion/parametros/<str:tipo>/nuevo/", editar_parametro, name="crear-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/editar/", editar_parametro, name="editar-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/estado/", cambiar_estado_parametro, name="cambiar-estado-parametro"),
]
