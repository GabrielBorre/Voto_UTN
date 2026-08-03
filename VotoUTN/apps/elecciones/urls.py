from django.urls import path
from .views import listar_elecciones

urlpatterns = [path("", listar_elecciones, name="lista-elecciones")]
