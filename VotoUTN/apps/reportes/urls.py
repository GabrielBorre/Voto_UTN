from django.urls import path

from apps.reportes.views import (
    exportar_reporte,
    generar_boletas_pdf_view,
    generar_padron_pdf_view,
    gestionar_reportes,
)


urlpatterns = [
    path("gestion/elecciones/<int:eleccion_id>/reportes/", gestionar_reportes, name="gestionar-reportes"),
    path("gestion/elecciones/<int:eleccion_id>/reportes/padron/pdf/", generar_padron_pdf_view, name="generar-padron-pdf"),
    path("gestion/elecciones/<int:eleccion_id>/reportes/boletas/pdf/", generar_boletas_pdf_view, name="generar-boletas-pdf"),
    path("gestion/elecciones/<int:eleccion_id>/reportes/<str:tipo>/", exportar_reporte, name="exportar-reporte"),
]
