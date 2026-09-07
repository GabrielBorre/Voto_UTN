from django.urls import path

from apps.mesas.views import gestionar_mesas


urlpatterns = [
    path(
        "gestion/elecciones/<int:eleccion_id>/mesas/",
        gestionar_mesas,
        name="gestionar-mesas",
    ),
]
