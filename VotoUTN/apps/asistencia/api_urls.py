from django.urls import path
from .api import APIVistaAsistenciaLote

urlpatterns = [path("elecciones/<int:eleccion_id>/asistencia/", APIVistaAsistenciaLote.as_view(), name="asistencia-batch-api")]
