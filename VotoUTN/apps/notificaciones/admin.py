from django.contrib import admin

from apps.notificaciones.models import EnvioNotificacion, PlantillaNotificacion


admin.site.register((PlantillaNotificacion, EnvioNotificacion))
