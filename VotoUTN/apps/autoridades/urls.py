from django.urls import path

from apps.autoridades.views import (
    descargar_plantilla_autoridades,
    gestionar_autoridades,
    mis_asignaciones_autoridad,
    preferencia_autoridad,
    responder_autoridad,
)


urlpatterns = [
    path("gestion/elecciones/<int:eleccion_id>/autoridades/", gestionar_autoridades, name="gestionar-autoridades"),
    path("gestion/elecciones/<int:eleccion_id>/autoridades/plantilla/", descargar_plantilla_autoridades, name="descargar-plantilla-autoridades"),
    path("autoridad/", mis_asignaciones_autoridad, name="mis-asignaciones-autoridad"),
    path("autoridad/asignaciones/<int:asignacion_id>/respuesta/", responder_autoridad, name="responder-autoridad"),
    path("autoridad/asignaciones/<int:asignacion_id>/preferencia/", preferencia_autoridad, name="preferencia-autoridad"),
]
