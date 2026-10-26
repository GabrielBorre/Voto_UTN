from django.db import transaction
from django.db.models.deletion import ProtectedError

from apps.auditoria.services import registrar_evento
from apps.parametros.models import Claustro
from .models import (
    Eleccion, EleccionClaustro, EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede, EleccionClaustroSede,
)


@transaction.atomic
def agregar_claustro(eleccion, claustro):
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado != Eleccion.Estado.BORRADOR:
        raise ValueError("Solo se pueden agregar claustros en estado En preparación.")
    if not claustro.activo:
        raise ValueError("El claustro seleccionado no está activo.")
    if eleccion.elecciones_claustro.filter(claustro=claustro).exists():
        raise ValueError("El claustro ya participa en esta elección.")
    configuracion = EleccionClaustro.objects.create(
        eleccion=eleccion, claustro=claustro,
        organizacion_departamentos=claustro.organizacion_departamentos,
    )
    sedes_ids = list(eleccion.elecciones_sede.values_list("sede_id", flat=True))
    EleccionClaustroSede.objects.bulk_create([
        EleccionClaustroSede(eleccion_claustro=configuracion, sede_id=sede_id)
        for sede_id in sedes_ids
    ])
    if claustro.organizacion_departamentos == Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO:
        alcance = EleccionClaustroDepartamento.objects.create(eleccion_claustro=configuracion)
        EleccionClaustroDepartamentoSede.objects.bulk_create([
            EleccionClaustroDepartamentoSede(eleccion_claustro_departamento=alcance, sede_id=sede_id)
            for sede_id in sedes_ids
        ])
    return configuracion


def eliminar_claustro(configuracion, usuario):
    try:
        with transaction.atomic():
            eleccion = Eleccion.objects.select_for_update().get(pk=configuracion.eleccion_id)
            if eleccion.estado != Eleccion.Estado.BORRADOR:
                raise ValueError("Solo se pueden eliminar claustros en estado En preparación.")
            identificador = configuracion.pk
            nombre = str(configuracion.claustro)
            EleccionClaustroDepartamentoSede.objects.filter(
                eleccion_claustro_departamento__eleccion_claustro=configuracion,
            ).delete()
            configuracion.departamentos.all().delete()
            configuracion.sedes_habilitadas.all().delete()
            configuracion.turnos_autoridad.all().delete()
            configuracion.delete()
            registrar_evento(
                accion="eleccion.claustro_eliminado", entidad="EleccionClaustro",
                entidad_id=identificador, eleccion=eleccion, usuario=usuario,
                datos_anteriores={"claustro": nombre},
            )
    except ProtectedError as error:
        raise ValueError(
            "No se puede eliminar un claustro con padrones, mesas u otros datos vinculados. "
            "No se modificó ningún dato."
        ) from error
