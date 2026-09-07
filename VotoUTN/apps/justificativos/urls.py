from django.urls import path

from apps.justificativos.views import bandeja_justificativos, gestionar_justificativos, mis_justificativos, resolver_justificativo


urlpatterns = [
    path("justificativos/", mis_justificativos, name="mis-justificativos"),
    path("gestion/justificativos/", bandeja_justificativos, name="bandeja-justificativos"),
    path("gestion/elecciones/<int:eleccion_id>/justificativos/", gestionar_justificativos, name="gestionar-justificativos"),
    path("gestion/justificativos/<int:justificativo_id>/resolver/", resolver_justificativo, name="resolver-justificativo"),
]
