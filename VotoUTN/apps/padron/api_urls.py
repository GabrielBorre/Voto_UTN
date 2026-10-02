from django.urls import path

from .api import APIVistaConsultaPadron


urlpatterns = [
    path("consulta/", APIVistaConsultaPadron.as_view(), name="api-consulta-padron"),
]