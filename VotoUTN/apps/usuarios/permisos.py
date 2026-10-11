from apps.usuarios.models import AsignacionRol
from apps.elecciones.models import Eleccion


ROLES_CON_PARTICIPACION = {
    AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
}


def es_administrativo_junta(usuario):
    if not usuario.is_authenticated or getattr(usuario, "es_elector", False):
        return False
    return AsignacionRol.objects.filter(
        usuario=usuario,
        activo=True,
        rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
    ).exists()


def puede_administrar_elecciones(usuario, eleccion=None):
    if not usuario.is_authenticated or getattr(usuario, "es_elector", False):
        return False
    if usuario.is_superuser:
        return True

    asignaciones = AsignacionRol.objects.filter(usuario=usuario, activo=True)
    if asignaciones.filter(rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        return True
    # El rol de administrador de junta es transversal: no depende de quién
    # creó la elección ni de la elección asociada al registro del rol.
    return asignaciones.filter(rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA).exists()


def puede_configurar_eleccion(usuario, eleccion):
    return (
        eleccion.estado != Eleccion.Estado.CERRADA
        and puede_administrar_elecciones(usuario, eleccion)
    )


def puede_crear_elecciones(usuario):
    if not usuario.is_authenticated or getattr(usuario, "es_elector", False):
        return False
    if usuario.is_superuser:
        return True
    asignaciones = AsignacionRol.objects.filter(usuario=usuario, activo=True)
    return asignaciones.filter(
        rol__in=(AsignacionRol.Rol.ADMINISTRADOR_SISTEMA, AsignacionRol.Rol.ADMINISTRADOR_JUNTA)
    ).exists()


def puede_administrar_parametros(usuario):
    if not usuario.is_authenticated or getattr(usuario, "es_elector", False):
        return False
    if usuario.is_superuser:
        return True
    return AsignacionRol.objects.filter(
        usuario=usuario,
        activo=True,
        rol__in=(
            AsignacionRol.Rol.ADMINISTRADOR_SISTEMA,
            AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        ),
    ).exists()


def puede_registrar_participacion(usuario, eleccion, mesa=None):
    if not usuario.is_authenticated or getattr(usuario, "es_elector", False):
        return False
    if usuario.is_superuser:
        return True

    asignaciones = AsignacionRol.objects.filter(usuario=usuario, activo=True)
    if asignaciones.filter(rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        return True
    if asignaciones.filter(rol=AsignacionRol.Rol.ADMINISTRATIVO_JUNTA).exists():
        return True

    asignaciones = asignaciones.filter(
        rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        eleccion=eleccion,
    )
    if mesa is None:
        return asignaciones.exists()
    return asignaciones.filter(mesa__isnull=True, sede__isnull=True).exists() or asignaciones.filter(mesa=mesa).exists() or asignaciones.filter(sede=mesa.sede, mesa__isnull=True).exists()


def puede_importar_padron(usuario, eleccion):
    return puede_configurar_eleccion(usuario, eleccion)


def puede_revisar_justificativo(usuario, eleccion):
    if not usuario.is_authenticated or getattr(usuario, "es_elector", False):
        return False
    if usuario.is_superuser:
        return True
    if es_administrativo_junta(usuario):
        return True
    return AsignacionRol.objects.filter(
        usuario=usuario,
        activo=True,
        eleccion=eleccion,
        rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    ).exists() or AsignacionRol.objects.filter(usuario=usuario, activo=True, rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists()


def elecciones_con_participacion(usuario):
    if getattr(usuario, "es_elector", False):
        return Eleccion.objects.none()
    elecciones = Eleccion.objects.filter(habilitada=True)
    if usuario.is_superuser or AsignacionRol.objects.filter(usuario=usuario, activo=True, rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        return elecciones
    if es_administrativo_junta(usuario):
        return elecciones
    return elecciones.filter(
        asignaciones_rol__usuario=usuario,
        asignaciones_rol__activo=True,
        asignaciones_rol__rol__in=ROLES_CON_PARTICIPACION,
    ).distinct()
