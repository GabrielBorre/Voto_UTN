from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Eleccion

@login_required
def listar_elecciones(request):
    return render(request, "elecciones/list.html", {"elecciones": Eleccion.objects.filter(is_active=True)})
