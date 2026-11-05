"""Compatibilidad con la antigua operación de promoción de suplentes."""

from django.core.exceptions import ValidationError


def puede_confirmar_reemplazo(usuario, eleccion):
    return False


def confirmar_reemplazo(asignacion, usuario):
    raise ValidationError("Las vacantes de autoridades permanecen sin cubrir; no se designan suplentes.")
