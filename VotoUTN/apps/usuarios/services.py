from apps.elecciones.models import ESTADOS_ELECCION_NO_CERRADOS
from apps.padron.models import Elector, RegistroPadron


def elector_de_identidad(usuario):
    """Obtiene el elector asociado a una identidad solo para autorizar acciones electorales."""
    perfil = getattr(usuario, "perfil_electoral", None)
    if perfil is not None and perfil.elector_id:
        return perfil.elector

    dni = getattr(usuario, "dni", None)
    if not dni:
        return None
    registro = RegistroPadron.objects.filter(
        eleccion__estado__in=ESTADOS_ELECCION_NO_CERRADOS,
        dni=dni,
        activo=True,
    ).select_related("elector").first()
    if registro is not None:
        return registro.elector
    electores = Elector.objects.filter(dni=dni)
    if electores.count() != 1:
        return None
    return electores.first()