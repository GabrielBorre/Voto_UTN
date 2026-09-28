from apps.padron.models import Elector


def elector_de_identidad(usuario):
    """Obtiene el elector asociado a una identidad solo para autorizar acciones electorales."""
    perfil = getattr(usuario, "perfil_electoral", None)
    if perfil is not None and perfil.elector_id:
        return perfil.elector

    dni = getattr(usuario, "dni", None)
    if not dni:
        return None
    return Elector.objects.filter(dni=dni).first()