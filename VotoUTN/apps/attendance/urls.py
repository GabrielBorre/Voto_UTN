from django.urls import path
from .views import scanner

urlpatterns = [path("eleccion/<int:election_id>/escanear/", scanner, name="scanner")]
