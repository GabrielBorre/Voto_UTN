from django.urls import path
from .views import (
    cambiar_estado_parametro,
    cambiar_estado_eleccion,
    crear_eleccion,
    editar_alcance_sedes,
    editar_eleccion,
    editar_parametro,
    gestionar_elecciones,
    gestionar_alcances,
    gestionar_mesas,
    gestionar_parametros,
    historial_elecciones,
    listar_elecciones,
    listar_parametros,
)

urlpatterns = [
    path("", listar_elecciones, name="lista-elecciones"),
    path("gestion/elecciones/", gestionar_elecciones, name="gestionar-elecciones"),
    path("gestion/elecciones/historial/", historial_elecciones, name="historial-elecciones"),
    path("gestion/elecciones/nueva/", crear_eleccion, name="crear-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/editar/", editar_eleccion, name="editar-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/estado/", cambiar_estado_eleccion, name="cambiar-estado-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/alcances/", gestionar_alcances, name="gestionar-alcances"),
    path("gestion/elecciones/<int:eleccion_id>/alcances/<str:tipo>/<int:objeto_id>/", editar_alcance_sedes, name="editar-alcance-sedes"),
    path("gestion/elecciones/<int:eleccion_id>/mesas/", gestionar_mesas, name="gestionar-mesas"),
    path("gestion/parametros/", gestionar_parametros, name="gestionar-parametros"),
    path("gestion/parametros/<str:tipo>/", listar_parametros, name="listar-parametros"),
    path("gestion/parametros/<str:tipo>/nuevo/", editar_parametro, name="crear-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/editar/", editar_parametro, name="editar-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/estado/", cambiar_estado_parametro, name="cambiar-estado-parametro"),
]
