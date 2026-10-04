from apps.autoridades.models import AsignacionAutoridad
from apps.usuarios.models import AsignacionRol
from apps.usuarios.permisos import (
    elecciones_con_participacion,
    puede_administrar_elecciones,
    puede_administrar_parametros,
    puede_crear_elecciones,
)
from apps.usuarios.services import elector_de_identidad


def navegacion_por_rol(request):
    usuario = request.user
    if not usuario.is_authenticated:
        return {}

    roles = set()
    es_elector = getattr(usuario, "es_elector", False)
    if not es_elector and not usuario.is_superuser:
        roles = set(
            AsignacionRol.objects.filter(usuario=usuario, activo=True).values_list("rol", flat=True)
        )
    es_elector = es_elector or AsignacionRol.Rol.ELECTOR in roles

    elector = elector_de_identidad(usuario)
    es_autoridad = AsignacionRol.Rol.AUTORIDAD_MESA in roles
    if elector is not None:
        es_autoridad = es_autoridad or AsignacionAutoridad.objects.filter(
            registro_padron__elector=elector
        ).exists()

    return {
        "nav_es_elector": es_elector,
        "nav_es_autoridad": es_autoridad,
        "nav_es_administrador_junta": AsignacionRol.Rol.ADMINISTRADOR_JUNTA in roles,
        "nav_es_administrativo_junta": AsignacionRol.Rol.ADMINISTRATIVO_JUNTA in roles,
        "nav_tiene_datos_elector": elector is not None,
        "nav_puede_ver_elecciones": not es_elector and elecciones_con_participacion(usuario).exists(),
        "nav_puede_gestionar_elecciones": puede_administrar_elecciones(usuario),
        "nav_puede_crear_elecciones": puede_crear_elecciones(usuario),
        "nav_puede_gestionar_parametros": puede_administrar_parametros(usuario),
        "nav_puede_revisar_justificativos": usuario.is_superuser
        or AsignacionRol.Rol.ADMINISTRADOR_SISTEMA in roles
        or AsignacionRol.Rol.ADMINISTRADOR_JUNTA in roles
        or AsignacionRol.Rol.ADMINISTRATIVO_JUNTA in roles,
        "nav_puede_ver_justificativos": elector is not None,
    }