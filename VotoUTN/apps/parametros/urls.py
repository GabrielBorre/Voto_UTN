from django.urls import path

from apps.parametros.views import cambiar_estado_parametro, editar_parametro, gestionar_parametros, listar_parametros


urlpatterns = [
    path("gestion/parametros/", gestionar_parametros, name="gestionar-parametros"),
    path("gestion/parametros/<str:tipo>/", listar_parametros, name="listar-parametros"),
    path("gestion/parametros/<str:tipo>/nuevo/", editar_parametro, name="crear-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/editar/", editar_parametro, name="editar-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/estado/", cambiar_estado_parametro, name="cambiar-estado-parametro"),
]
