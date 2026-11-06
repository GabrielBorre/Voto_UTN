from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from apps.elecciones.models import Eleccion
from apps.mesas.models import Mesa
from apps.usuarios.permisos import puede_registrar_participacion
from .services import ErrorEscaneoMesa, ServicioRegistroParticipacion

FILTROS_TABLERO = ("claustro", "sede", "departamento", "escaneo", "pagina")

@login_required
def escanear(request, eleccion_id):
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id, habilitada=True, estado=Eleccion.Estado.EN_CURSO)
    if not puede_registrar_participacion(request.user, eleccion):
        return render(request, "403.html", status=403)
    return render(request, "asistencia/scanner.html", {"eleccion": eleccion})


@login_required
def procesar_mesa_manual(request, eleccion_id, mesa_id):
    if request.method != "POST":
        raise Http404()
    eleccion = get_object_or_404(Eleccion, pk=eleccion_id, habilitada=True, estado=Eleccion.Estado.EN_CURSO)
    mesa = get_object_or_404(Mesa.objects.select_related("eleccion"), pk=mesa_id, eleccion=eleccion)
    if not puede_registrar_participacion(request.user, eleccion, mesa):
        return render(request, "403.html", status=403)
    try:
        ServicioRegistroParticipacion.procesar_mesa_manual(mesa=mesa, usuario=request.user)
    except ErrorEscaneoMesa as error:
        messages.error(request, f"Mesa {mesa.codigo}: {error.mensaje}")
    else:
        messages.success(request, f"La mesa {mesa.codigo} quedó registrada como procesada.")

    filtros_enviados = QueryDict(request.POST.get("filtros", ""))
    parametros = QueryDict(mutable=True)
    parametros["eleccion"] = str(eleccion.pk)
    for nombre in FILTROS_TABLERO:
        valor = filtros_enviados.get(nombre)
        if valor:
            parametros[nombre] = valor
    return redirect(f"{reverse('lista-elecciones')}?{parametros.urlencode()}#mesas-pendientes")
