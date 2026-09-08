from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_administrar_elecciones


@login_required
def gestionar_mesas(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id)
    if not puede_administrar_elecciones(request.user, eleccion):
        return HttpResponseForbidden("No tiene permiso para gestionar esta eleccion.")

    mesas = eleccion.mesas.select_related(
        "sede",
        "turno",
        "eleccion_claustro_departamento__eleccion_claustro__claustro",
        "eleccion_claustro_departamento__departamento",
    )
    return render(
        request,
        "mesas/gestion.html",
        {"eleccion": eleccion, "mesas": mesas},
    )
