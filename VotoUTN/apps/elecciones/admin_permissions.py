from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.elecciones.models import Eleccion


class EleccionCerradaAdminMixin(admin.ModelAdmin):
    def _eleccion_asociada(self, objeto, visitados=None):
        if isinstance(objeto, Eleccion):
            return objeto
        if objeto is None:
            return None

        visitados = visitados or set()
        clave = (objeto._meta.label_lower, objeto.pk)
        if clave in visitados:
            return None
        visitados.add(clave)

        for campo in objeto._meta.fields:
            if not campo.is_relation or not campo.many_to_one or campo.auto_created:
                continue
            if getattr(objeto, f"{campo.name}_id", None) is None:
                continue
            eleccion = self._eleccion_asociada(getattr(objeto, campo.name), visitados)
            if eleccion is not None:
                return eleccion
        return None

    def _esta_cerrada(self, objeto):
        eleccion = self._eleccion_asociada(objeto)
        return eleccion is not None and eleccion.estado == Eleccion.Estado.CERRADA

    def has_change_permission(self, request, obj=None):
        return not self._esta_cerrada(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self._esta_cerrada(obj) and super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if self._esta_cerrada(obj):
            raise PermissionDenied("No se puede modificar la configuracion de una eleccion cerrada.")
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        if self._esta_cerrada(obj):
            raise PermissionDenied("No se puede modificar la configuracion de una eleccion cerrada.")
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        if any(self._esta_cerrada(obj) for obj in queryset):
            raise PermissionDenied("No se puede modificar la configuracion de una eleccion cerrada.")
        super().delete_queryset(request, queryset)
