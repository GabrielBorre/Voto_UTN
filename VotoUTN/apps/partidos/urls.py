from django.urls import path

from apps.partidos.views import (
    cambiar_estado_candidato,
    cambiar_estado_lista,
    cambiar_estado_participacion,
    cambiar_estado_puesto_eleccion,
    detalle_lista,
    detalle_participacion,
    descargar_plantilla_candidaturas,
    editar_candidato,
    editar_puesto_eleccion,
    confirmar_importacion,
    gestionar_partidos,
    importar_candidaturas,
)


urlpatterns = [
    path("gestion/elecciones/<int:eleccion_id>/partidos/", gestionar_partidos, name="gestionar-partidos"),
    path("gestion/elecciones/<int:eleccion_id>/candidaturas/importar/", importar_candidaturas, name="importar-candidaturas"),
    path("gestion/elecciones/<int:eleccion_id>/candidaturas/plantilla.csv", descargar_plantilla_candidaturas, name="plantilla-candidaturas"),
    path("gestion/elecciones/<int:eleccion_id>/candidaturas/puestos/<int:puesto_id>/editar/", editar_puesto_eleccion, name="editar-puesto-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/candidaturas/puestos/<int:puesto_id>/estado/", cambiar_estado_puesto_eleccion, name="cambiar-estado-puesto-eleccion"),
    path("gestion/elecciones/<int:eleccion_id>/candidaturas/importaciones/<int:importacion_id>/confirmar/", confirmar_importacion, name="confirmar-importacion-candidaturas"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/<int:participacion_id>/", detalle_participacion, name="detalle-participacion-partido"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/<int:participacion_id>/estado/", cambiar_estado_participacion, name="cambiar-estado-participacion-partido"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/listas/<int:lista_id>/", detalle_lista, name="detalle-lista-candidatos"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/listas/<int:lista_id>/estado/", cambiar_estado_lista, name="cambiar-estado-lista-candidatos"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/candidatos/<int:candidato_id>/editar/", editar_candidato, name="editar-candidato"),
    path("gestion/elecciones/<int:eleccion_id>/partidos/candidatos/<int:candidato_id>/estado/", cambiar_estado_candidato, name="cambiar-estado-candidato"),
]
