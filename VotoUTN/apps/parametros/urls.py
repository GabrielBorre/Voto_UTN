from django.urls import path

from apps.parametros.views import (
    cambiar_estado_parametro,
    editar_comunicacion_fecha,
    editar_parametro,
    editar_variante_comunicacion,
    gestionar_comunicaciones_fecha,
    gestionar_parametros,
    listar_parametros,
    previsualizar_plantilla,
)


urlpatterns = [
    path("gestion/parametros/", gestionar_parametros, name="gestionar-parametros"),
    path("gestion/parametros/<str:tipo>/", listar_parametros, name="listar-parametros"),
    path("gestion/parametros/<str:tipo>/nuevo/", editar_parametro, name="crear-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/editar/", editar_parametro, name="editar-parametro"),
    path("gestion/parametros/<str:tipo>/<int:objeto_id>/estado/", cambiar_estado_parametro, name="cambiar-estado-parametro"),
    path("gestion/parametros/fechas-administrativas/<int:fecha_id>/comunicaciones/", gestionar_comunicaciones_fecha, name="comunicaciones-fecha"),
    path("gestion/parametros/fechas-administrativas/<int:fecha_id>/comunicaciones/nueva/", editar_comunicacion_fecha, name="crear-comunicacion-fecha"),
    path("gestion/parametros/fechas-administrativas/<int:fecha_id>/comunicaciones/<int:comunicacion_id>/editar/", editar_comunicacion_fecha, name="editar-comunicacion-fecha"),
    path("gestion/parametros/comunicaciones/<int:comunicacion_id>/variantes/nueva/", editar_variante_comunicacion, name="crear-variante-comunicacion"),
    path("gestion/parametros/comunicaciones/<int:comunicacion_id>/variantes/<int:variante_id>/editar/", editar_variante_comunicacion, name="editar-variante-comunicacion"),
    path("gestion/parametros/plantillas-mensajes/<int:plantilla_id>/previsualizar/", previsualizar_plantilla, name="previsualizar-plantilla"),
]
