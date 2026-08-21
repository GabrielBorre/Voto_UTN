from .models import EnvioNotificacion


def notificaciones_usuario(request):
    cantidad = 0
    if request.user.is_authenticated:
        cantidad = EnvioNotificacion.objects.filter(destinatario=request.user, leida_en__isnull=True).count()
    return {"notificaciones_no_leidas": cantidad}
