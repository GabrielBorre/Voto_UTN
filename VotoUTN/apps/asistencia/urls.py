from django.urls import path
from .views import escanear

urlpatterns = [path("eleccion/<int:eleccion_id>/escanear/", escanear, name="escanear")]
