from django.urls import path

from apps.notificaciones.views import gestionar_notificaciones, leer_notificacion, mis_notificaciones


urlpatterns = [
    path("gestion/notificaciones/", gestionar_notificaciones, name="gestionar-notificaciones"),
    path("notificaciones/", mis_notificaciones, name="mis-notificaciones"),
    path("notificaciones/<int:notificacion_id>/", leer_notificacion, name="leer-notificacion"),
]
