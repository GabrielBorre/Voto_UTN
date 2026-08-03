from django.urls import path
from .views import crear_eleccion, gestionar_elecciones, gestionar_mesas, listar_elecciones

urlpatterns = [
    path("", listar_elecciones, name="lista-elecciones"),
    path("gestion/elecciones/", gestionar_elecciones, name="gestionar-elecciones"),
    path("gestion/elecciones/nueva/", crear_eleccion, name="crear-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/mesas/", gestionar_mesas, name="gestionar-mesas"),
]
