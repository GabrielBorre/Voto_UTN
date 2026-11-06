from django.urls import path

from apps.autoridades.views import (
    descargar_plantilla_autoridades,
    gestionar_autoridades,
    gestionar_autoridades_claustro,
    mis_asignaciones_autoridad,
    preferencia_autoridad,
    responder_autoridad,
    seleccionar_autoridades_mesa,
    confirmar_reemplazo_autoridad,
    descargar_importacion_nomina,
    confirmar_traslado_vacante,
    confirmar_autoridades_definitivas,
    previsualizar_recalculo_mesas,
    revisar_retorno_votacion,
)


urlpatterns = [
    path("gestion/autoridades/<int:asignacion_id>/retorno-votacion/", revisar_retorno_votacion, name="revisar-retorno-votacion"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/recalcular-mesas/", previsualizar_recalculo_mesas, name="previsualizar-recalculo-mesas"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/confirmar/", confirmar_autoridades_definitivas, name="confirmar-autoridades-definitivas"),
    path("gestion/autoridades/<int:asignacion_id>/traslado-vacante/", confirmar_traslado_vacante, name="confirmar-traslado-vacante"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/<int:claustro_id>/importaciones/<int:importacion_id>/archivo/", descargar_importacion_nomina, name="descargar-importacion-nomina"),
    path("gestion/autoridades/<int:asignacion_id>/reemplazo/", confirmar_reemplazo_autoridad, name="confirmar-reemplazo-autoridad"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/<int:claustro_id>/mesas/<int:mesa_id>/", seleccionar_autoridades_mesa, name="seleccionar-autoridades-mesa"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/", gestionar_autoridades, name="gestionar-autoridades"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/plantilla/", descargar_plantilla_autoridades, name="descargar-plantilla-autoridades"),
    path(
        "gestion/elecciones/<int:eleccion_id>/autoridades/<int:claustro_id>/",
        gestionar_autoridades_claustro,
        name="gestionar-autoridades-claustro",
    ),
    path(
        "gestion/elecciones/<int:eleccion_id>/autoridades/<int:claustro_id>/plantilla/",
        descargar_plantilla_autoridades,
        name="descargar-plantilla-autoridades-claustro",
    ),
    path("autoridad/", mis_asignaciones_autoridad, name="mis-asignaciones-autoridad"),
    path("autoridad/asignaciones/<int:asignacion_id>/respuesta/", responder_autoridad, name="responder-autoridad"),
    path("autoridad/asignaciones/<int:asignacion_id>/preferencia/", preferencia_autoridad, name="preferencia-autoridad"),
]
