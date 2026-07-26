from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from apps.elecciones.models import Eleccion

@login_required
def escanear(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id, is_active=True)
    return render(request, "asistencia/scanner.html", {"eleccion": eleccion})
