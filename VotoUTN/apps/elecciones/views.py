from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Eleccion
from apps.usuarios.permisos import elecciones_con_participacion

@login_required
def listar_elecciones(request):
    return render(request, "elecciones/list.html", {"elecciones": elecciones_con_participacion(request.user)})
