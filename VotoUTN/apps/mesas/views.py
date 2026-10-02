from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
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
        "eleccion_claustro_departamento__eleccion_claustro__claustro",
        "eleccion_claustro_departamento__departamento",
    )
    resumen = mesas.aggregate(
        total=Count("id"),
        automaticas=Count("id", filter=Q(generada_automaticamente=True)),
        claustros=Count(
            "eleccion_claustro_departamento__eleccion_claustro_id",
            distinct=True,
        ),
        sedes=Count("sede_id", distinct=True),
    )
    return render(
        request,
        "mesas/gestion.html",
        {"eleccion": eleccion, "mesas": mesas, "resumen": resumen},
    )
