from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_registrar_participacion

@login_required
def escanear(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id, habilitada=True)
    if not puede_registrar_participacion(request.user, eleccion):
        return render(request, "403.html", status=403)
    return render(request, "asistencia/scanner.html", {"eleccion": eleccion})
