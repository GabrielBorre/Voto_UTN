from apps.notificaciones.services import notificaciones_para_usuario


def notificaciones_usuario(request):
    cantidad = notificaciones_para_usuario(request.user).filter(leida_en__isnull=True).count()
    return {"notificaciones_no_leidas": cantidad}
