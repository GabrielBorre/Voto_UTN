from django.urls import path

from apps.padron.views import (
    confirmar_importacion_padron,
    descargar_errores_importacion,
    descargar_plantilla_padron,
    detalle_importacion_padron,
    historial_importaciones_padron,
    previsualizar_padron,
)


urlpatterns = [
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/plantilla/", descargar_plantilla_padron, name="descargar-plantilla-padron"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/padron/", previsualizar_padron, name="previsualizar-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/", historial_importaciones_padron, name="historial-importaciones-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/<int:importacion_id>/", detalle_importacion_padron, name="detalle-importacion-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/<int:importacion_id>/confirmar/", confirmar_importacion_padron, name="confirmar-importacion-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/<int:importacion_id>/errores/", descargar_errores_importacion, name="descargar-errores-importacion"),
]
