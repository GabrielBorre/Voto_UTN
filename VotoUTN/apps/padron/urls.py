from django.urls import path

from apps.padron.views import (
    confirmar_importacion_padron,
    configurar_sedes_claustro,
    descargar_errores_importacion,
    descargar_plantilla_padron,
    exportar_padron_claustro,
    detalle_importacion_padron,
    eliminar_padron_claustro,
    gestionar_solicitudes_cambio_sede,
    historial_importaciones_padron,
    mis_solicitudes_cambio_sede,
    previsualizar_padron,
)


urlpatterns = [
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/padron/exportar/<str:formato>/", exportar_padron_claustro, name="exportar-padron-claustro"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/plantilla/", descargar_plantilla_padron, name="descargar-plantilla-padron"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/padron/", previsualizar_padron, name="previsualizar-padron"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/padron/eliminar/", eliminar_padron_claustro, name="eliminar-padron-claustro"),
    path("gestion/elecciones/<int:eleccion_id>/preparar/<int:claustro_id>/padron/sedes/", configurar_sedes_claustro, name="configurar-sedes-claustro"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/", historial_importaciones_padron, name="historial-importaciones-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/<int:importacion_id>/", detalle_importacion_padron, name="detalle-importacion-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/<int:importacion_id>/confirmar/", confirmar_importacion_padron, name="confirmar-importacion-padron"),
    path("gestion/elecciones/<int:eleccion_id>/padrones/<int:importacion_id>/errores/", descargar_errores_importacion, name="descargar-errores-importacion"),
    path("elecciones/mis-solicitudes-cambio-sede/", mis_solicitudes_cambio_sede, name="mis-solicitudes-cambio-sede"),
    path(
        "gestion/elecciones/<int:eleccion_id>/solicitudes-cambio-sede/",
        gestionar_solicitudes_cambio_sede,
        name="gestionar-solicitudes-cambio-sede",
    ),
]
