from django.urls import path
from .api import APIVistaAsistenciaLote, APIVistaEscaneoMesa

urlpatterns = [
    path("elecciones/<int:eleccion_id>/asistencia/", APIVistaAsistenciaLote.as_view(), name="api-asistencia-lote"),
    path("elecciones/<int:eleccion_id>/asistencia/mesa/", APIVistaEscaneoMesa.as_view(), name="api-asistencia-mesa"),
]
