from django.urls import path

from apps.justificativos.views import (
    bandeja_justificativos,
    detalle_justificativo_elector,
    documento_justificativo_elector,
    documento_justificativo_gestion,
    gestionar_justificativos,
    mis_justificativos,
    resolver_justificativo,
)


urlpatterns = [
    path("justificativos/", mis_justificativos, name="mis-justificativos"),
    path("justificativos/<int:justificativo_id>/", detalle_justificativo_elector, name="detalle-justificativo-elector"),
    path("justificativos/<int:justificativo_id>/documento/", documento_justificativo_elector, name="documento-justificativo-elector"),
    path("gestion/justificativos/<int:justificativo_id>/documento/", documento_justificativo_gestion, name="documento-justificativo-gestion"),
    path("gestion/justificativos/", bandeja_justificativos, name="bandeja-justificativos"),
    path("gestion/elecciones/<int:eleccion_id>/justificativos/", gestionar_justificativos, name="gestionar-justificativos"),
    path("gestion/justificativos/<int:justificativo_id>/resolver/", resolver_justificativo, name="resolver-justificativo"),
]
