from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.elecciones.urls")),
    path("asistencia/", include("apps.asistencia.urls")),
    path("api/", include("apps.asistencia.api_urls")),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("pagina_web/",include("apps.pagina_web.urls")),
]
