import csv
import io

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron


CABECERAS_AUTORIDADES = ("dni", "legajo", "nombres", "apellidos", "mail", "claustro", "departamento")


@transaction.atomic
def asignar_autoridad(registro_padron, mesa, usuario):
    if AsignacionAutoridad.objects.filter(mesa=mesa).exclude(estado=AsignacionAutoridad.Estado.RECHAZADA).count() >= mesa.eleccion.maximo_autoridades_por_mesa:
        raise ValidationError("La mesa ya alcanzo el maximo de autoridades configurado.")
    candidatura, _ = CandidaturaAutoridad.objects.get_or_create(registro_padron=registro_padron, defaults={"cargada_por": usuario})
    asignacion, creada = AsignacionAutoridad.objects.get_or_create(
        registro_padron=registro_padron,
        defaults={"mesa": mesa, "candidatura": candidatura, "asignada_por": usuario},
    )
    if not creada and asignacion.mesa_id != mesa.id:
        raise ValidationError("El elector ya fue asignado como autoridad de otra mesa.")
    asignacion.full_clean()
    return asignacion, creada


def validar_csv_autoridades(contenido, eleccion):
    try:
        lector = csv.DictReader(io.StringIO(contenido.decode("utf-8-sig"), newline=""))
    except UnicodeDecodeError:
        return [], [(None, "El archivo debe estar codificado en UTF-8.")]
    cabeceras = tuple((cabecera or "").strip().lower() for cabecera in (lector.fieldnames or []))
    if cabeceras != CABECERAS_AUTORIDADES:
        return [], [(None, "Las cabeceras deben ser: dni, legajo, nombres, apellidos, mail, claustro, departamento.")]
    filas, errores = [], []
    vistos = set()
    for numero, original in enumerate(lector, start=2):
        fila = {campo: (original.get(campo) or "").strip() for campo in CABECERAS_AUTORIDADES}
        filas.append(fila)
        clave = (fila["dni"], fila["legajo"])
        if clave in vistos:
            errores.append((numero, "El elector esta repetido en el archivo."))
        vistos.add(clave)
        padron = RegistroPadron.objects.filter(eleccion=eleccion, elector__dni=fila["dni"], elector__legajo=fila["legajo"], activo=True, eleccion_claustro_departamento__eleccion_claustro__claustro__nombre__iexact=fila["claustro"], eleccion_claustro_departamento__departamento__codigo__iexact=fila["departamento"]).first()
        if padron is None:
            errores.append((numero, "El elector no pertenece al padron de esta eleccion."))
    return filas, errores


@transaction.atomic
def importar_autoridades(contenido, eleccion, usuario):
    filas, errores = validar_csv_autoridades(contenido, eleccion)
    if errores:
        return 0, errores
    creadas = 0
    for fila in filas:
        padron = RegistroPadron.objects.get(eleccion=eleccion, elector__dni=fila["dni"], elector__legajo=fila["legajo"])
        _, creada = CandidaturaAutoridad.objects.get_or_create(registro_padron=padron, defaults={"cargada_por": usuario})
        creadas += int(creada)
    return creadas, []


@transaction.atomic
def responder_asignacion(asignacion, aceptar):
    asignacion.estado = AsignacionAutoridad.Estado.CONFIRMADA if aceptar else AsignacionAutoridad.Estado.RECHAZADA
    asignacion.respondida_en = timezone.now()
    asignacion.save(update_fields=("estado", "respondida_en"))
