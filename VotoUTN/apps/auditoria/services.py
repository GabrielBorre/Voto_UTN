from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

from .models import EventoAuditoria


def obtener_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or None
    return request.META.get("REMOTE_ADDR")


def obtener_agente_usuario(request: HttpRequest | None) -> str:
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:300]


def registrar_evento(
    *,
    accion: str,
    entidad: str,
    entidad_id: Any = "",
    eleccion=None,
    usuario=None,
    request: HttpRequest | None = None,
    datos_anteriores: dict[str, Any] | None = None,
    datos_nuevos: dict[str, Any] | None = None,
) -> EventoAuditoria:
    usuario_auditoria = usuario
    if usuario_auditoria is None and request is not None:
        usuario_auditoria = getattr(request, "user", None)
    if isinstance(usuario_auditoria, AnonymousUser) or not getattr(usuario_auditoria, "is_authenticated", False):
        usuario_auditoria = None

    return EventoAuditoria.objects.create(
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id or ""),
        eleccion=eleccion,
        usuario=usuario_auditoria,
        datos_anteriores=datos_anteriores or {},
        datos_nuevos=datos_nuevos or {},
        ip=obtener_ip(request),
        agente_usuario=obtener_agente_usuario(request),
    )
