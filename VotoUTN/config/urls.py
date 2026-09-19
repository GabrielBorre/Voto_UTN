from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from .views import keycloak_login_view, keycloak_login_callback_view, keycloak_logout_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.elecciones.urls")),
    path("", include("apps.reportes.urls")),
    path("", include("apps.padron.urls")),
    path("", include("apps.justificativos.urls")),
    path("", include("apps.autoridades.urls")),
    path("", include("apps.notificaciones.urls")),
    path("", include("apps.parametros.urls")),
    path("", include("apps.mesas.urls")),
    path("", include("apps.partidos.urls")),
    path("asistencia/", include("apps.asistencia.urls")),
    path("api/", include("apps.asistencia.api_urls")),
    path('login/', keycloak_login_view, name='keycloak_login'),
    path('callback', keycloak_login_callback_view, name='callback_login'),
    path("logout/", keycloak_logout_view, name="logout"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
