from django.urls import path
from .views import escanear, procesar_mesa_manual

urlpatterns = [
    path("eleccion/<int:eleccion_id>/escanear/", escanear, name="escanear"),
    path(
        "eleccion/<int:eleccion_id>/mesas/<int:mesa_id>/procesar/",
        procesar_mesa_manual,
        name="procesar-mesa-manual",
    ),
]
