from apps.usuarios.models import AsignacionRol
from apps.elecciones.models import Eleccion


ROLES_CON_PARTICIPACION = {
    AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
    AsignacionRol.Rol.ADMINISTRATIVO_JUNTA,
}


def puede_administrar_elecciones(usuario, eleccion=None):
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True

    asignaciones = AsignacionRol.objects.filter(usuario=usuario, activo=True)
    if asignaciones.filter(rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        return True
    if eleccion is None:
        return False
    return asignaciones.filter(
        rol=AsignacionRol.Rol.ADMINISTRADOR_JUNTA,
        eleccion=eleccion,
    ).exists()


def puede_registrar_participacion(usuario, eleccion, mesa=None):
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True

    asignaciones = AsignacionRol.objects.filter(usuario=usuario, activo=True)
    if asignaciones.filter(rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        return True

    asignaciones = asignaciones.filter(rol__in=ROLES_CON_PARTICIPACION, eleccion=eleccion)
    if mesa is None:
        return asignaciones.exists()
    return asignaciones.filter(mesa__isnull=True, sede__isnull=True).exists() or asignaciones.filter(mesa=mesa).exists() or asignaciones.filter(sede=mesa.sede, mesa__isnull=True).exists()


def elecciones_con_participacion(usuario):
    elecciones = Eleccion.objects.filter(habilitada=True)
    if usuario.is_superuser or AsignacionRol.objects.filter(usuario=usuario, activo=True, rol=AsignacionRol.Rol.ADMINISTRADOR_SISTEMA).exists():
        return elecciones
    return elecciones.filter(
        asignaciones_rol__usuario=usuario,
        asignaciones_rol__activo=True,
        asignaciones_rol__rol__in=ROLES_CON_PARTICIPACION,
    ).distinct()
