from django.urls import path

from apps.partidos.views import (
    cambiar_estado_candidato,
    cambiar_estado_lista,
    cambiar_estado_participacion,
    detalle_lista,
    detalle_participacion,
    editar_candidato,
    gestionar_partidos,
)


urlpatterns = [
    path("gestion/elecciones/<int:eleccion_id>/partidos/", gestionar_partidos, name="gestionar-partidos"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/<int:participacion_id>/", detalle_participacion, name="detalle-participacion-partido"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/<int:participacion_id>/estado/", cambiar_estado_participacion, name="cambiar-estado-participacion-partido"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/listas/<int:lista_id>/", detalle_lista, name="detalle-lista-candidatos"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/listas/<int:lista_id>/estado/", cambiar_estado_lista, name="cambiar-estado-lista-candidatos"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/candidatos/<int:candidato_id>/editar/", editar_candidato, name="editar-candidato"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/candidatos/<int:candidato_id>/estado/", cambiar_estado_candidato, name="cambiar-estado-candidato"),
]
