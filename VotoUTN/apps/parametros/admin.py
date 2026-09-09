from django.contrib import admin

from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


admin.site.register((Sede, Claustro, Turno, Departamento, FechaAdministrativa))
