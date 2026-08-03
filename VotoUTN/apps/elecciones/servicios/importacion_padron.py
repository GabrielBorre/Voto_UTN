import csv
import hashlib
import io
from collections import defaultdict
from dataclasses import dataclass

from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.elecciones.models import (
    AsignacionMesa,
    Departamento,
    Elector,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    ErrorImportacionPadron,
    ImportacionPadron,
    Mesa,
    RegistroPadron,
    Sede,
)


CABECERAS_PADRON = ("dni", "legajo", "nombres", "apellidos", "mail", "departamento", "sede")
CARACTERES_FORMULA = ("=", "+", "-", "@")


@dataclass
class ResultadoValidacion:
    filas: list[dict[str, str]]
    errores: list[tuple[int | None, str, str]]


def validar_csv_padron(contenido: bytes, eleccion_claustro) -> ResultadoValidacion:
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ResultadoValidacion([], [(None, "archivo", "El archivo debe estar codificado en UTF-8.")])

    lector = csv.DictReader(io.StringIO(texto, newline=""))
    cabeceras = tuple((cabecera or "").strip().lower() for cabecera in (lector.fieldnames or []))
    if cabeceras != CABECERAS_PADRON:
        return ResultadoValidacion([], [(None, "archivo", "Las cabeceras deben ser: dni, legajo, nombres, apellidos, mail, departamento, sede.")])

    configuraciones = {
        configuracion.departamento.codigo.casefold(): configuracion
        for configuracion in EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro=eleccion_claustro,
            departamento__activo=True,
        ).select_related("departamento")
    }
    sedes_permitidas = {
        (habilitacion.eleccion_claustro_departamento_id, habilitacion.sede.nombre.casefold())
        for habilitacion in EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            sede__activa=True,
        ).select_related("sede")
    }
    filas, errores = [], []
    vistos = defaultdict(set)
    for numero_fila, fila_original in enumerate(lector, start=2):
        fila = {campo: (fila_original.get(campo) or "").strip() for campo in CABECERAS_PADRON}
        filas.append(fila)
        for campo, valor in fila.items():
            if valor.startswith(CARACTERES_FORMULA):
                errores.append((numero_fila, campo, "No se permiten valores que comiencen con caracteres de formula."))
        if not fila["dni"].isdigit() or not 7 <= len(fila["dni"]) <= 12:
            errores.append((numero_fila, "dni", "El DNI debe contener entre 7 y 12 digitos."))
        if not fila["legajo"]:
            errores.append((numero_fila, "legajo", "El legajo es obligatorio."))
        if not fila["nombres"] or not fila["apellidos"]:
            errores.append((numero_fila, "nombres", "Nombres y apellidos son obligatorios."))
        try:
            validate_email(fila["mail"])
        except Exception:
            errores.append((numero_fila, "mail", "El correo electronico no tiene un formato valido."))
        for campo in ("dni", "legajo"):
            if fila[campo] and fila[campo] in vistos[campo]:
                errores.append((numero_fila, campo, f"El {campo} esta repetido dentro del archivo."))
            vistos[campo].add(fila[campo])
        configuracion = configuraciones.get(fila["departamento"].casefold())
        if configuracion is None:
            errores.append((numero_fila, "departamento", "El departamento no fue habilitado para este claustro."))
        elif (configuracion.id, fila["sede"].casefold()) not in sedes_permitidas:
            errores.append((numero_fila, "sede", "La sede no esta habilitada para este departamento."))
        elector_dni = Elector.objects.filter(dni=fila["dni"]).first()
        elector_legajo = Elector.objects.filter(legajo=fila["legajo"]).first()
        if elector_dni and elector_legajo and elector_dni.pk != elector_legajo.pk:
            errores.append((numero_fila, "dni", "El DNI y el legajo ya pertenecen a electores distintos."))
        else:
            elector_existente = elector_dni or elector_legajo
            if elector_existente and (elector_existente.dni != fila["dni"] or elector_existente.legajo != fila["legajo"]):
                errores.append((numero_fila, "legajo", "El DNI o el legajo no coincide con el elector existente."))
            if elector_existente and configuracion:
                registro = RegistroPadron.objects.filter(elector=elector_existente, eleccion=eleccion_claustro.eleccion).first()
                if registro and registro.eleccion_claustro_departamento_id != configuracion.id:
                    errores.append((numero_fila, "departamento", "El elector ya pertenece a otro claustro o departamento en esta elección."))
    if not filas and not errores:
        errores.append((None, "archivo", "El archivo no contiene filas de padron."))
    return ResultadoValidacion(filas, errores)


def registrar_errores(importacion, errores):
    ErrorImportacionPadron.objects.filter(importacion=importacion).delete()
    ErrorImportacionPadron.objects.bulk_create([
        ErrorImportacionPadron(importacion=importacion, fila=fila, campo=campo, mensaje=mensaje)
        for fila, campo, mensaje in errores
    ])


def generar_mesas_automaticas(eleccion_claustro):
    maximo = eleccion_claustro.maximo_votantes_por_mesa
    if not maximo:
        raise ValueError("Debe definir el maximo de electores por mesa antes de confirmar el padron.")
    eleccion = eleccion_claustro.eleccion
    turno_relacion = eleccion.elecciones_turno.select_related("turno").order_by("turno__hora_inicio", "turno__nombre").first()
    if turno_relacion is None:
        raise ValueError("La eleccion debe tener al menos un turno habilitado.")

    mesas_anteriores = Mesa.objects.filter(
        eleccion=eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        generada_automaticamente=True,
    )
    AsignacionMesa.objects.filter(mesa__in=mesas_anteriores).delete()
    mesas_anteriores.delete()

    padrones = RegistroPadron.objects.filter(
        eleccion=eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        sede__isnull=False,
    ).select_related("elector", "sede", "eleccion_claustro_departamento__departamento").order_by(
        "eleccion_claustro_departamento__departamento__nombre", "sede__nombre", "elector__nombre", "elector__legajo"
    )
    grupos = defaultdict(list)
    for padron in padrones:
        grupos[(padron.eleccion_claustro_departamento, padron.sede)].append(padron)

    ultimo_numero = Mesa.objects.filter(eleccion=eleccion).order_by("-numero").values_list("numero", flat=True).first() or 0
    mesas, asignaciones = [], []
    for (configuracion, sede), registros in grupos.items():
        for inicio in range(0, len(registros), maximo):
            ultimo_numero += 1
            mesas.append(Mesa(
                eleccion=eleccion,
                numero=ultimo_numero,
                eleccion_claustro_departamento=configuracion,
                sede=sede,
                turno=turno_relacion.turno,
                generada_automaticamente=True,
            ))
    Mesa.objects.bulk_create(mesas)

    indice_mesa = 0
    for registros in grupos.values():
        for inicio in range(0, len(registros), maximo):
            mesa = mesas[indice_mesa]
            indice_mesa += 1
            asignaciones.extend(AsignacionMesa(registro_padron=padron, mesa=mesa) for padron in registros[inicio:inicio + maximo])
    AsignacionMesa.objects.bulk_create(asignaciones)
    return len(mesas)


@transaction.atomic
def confirmar_importacion(importacion):
    if importacion.estado == ImportacionPadron.Estado.CONFIRMADA:
        return 0
    importacion.archivo.open("rb")
    try:
        contenido = importacion.archivo.read()
    finally:
        importacion.archivo.close()
    if hashlib.sha256(contenido).hexdigest() != importacion.huella_archivo:
        raise ValueError("El archivo almacenado no coincide con el archivo previsualizado.")
    resultado = validar_csv_padron(contenido, importacion.eleccion_claustro)
    if resultado.errores:
        registrar_errores(importacion, resultado.errores)
        importacion.cantidad_filas = len(resultado.filas)
        importacion.cantidad_validas = 0
        importacion.cantidad_errores = len(resultado.errores)
        importacion.estado = ImportacionPadron.Estado.RECHAZADA
        importacion.save(update_fields=("cantidad_filas", "cantidad_validas", "cantidad_errores", "estado"))
        raise ValueError("El archivo cambio o ya no cumple las validaciones.")

    configuraciones = {
        configuracion.departamento.codigo.casefold(): configuracion
        for configuracion in EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro=importacion.eleccion_claustro,
        ).select_related("departamento")
    }
    sedes = {sede.nombre.casefold(): sede for sede in Sede.objects.filter(activa=True)}
    cantidad_creada = 0
    for fila in resultado.filas:
        elector_dni = Elector.objects.filter(dni=fila["dni"]).first()
        elector_legajo = Elector.objects.filter(legajo=fila["legajo"]).first()
        if elector_dni and elector_legajo and elector_dni.pk != elector_legajo.pk:
            raise ValueError("El padrón contiene un DNI y un legajo asociados a electores distintos.")
        elector = elector_dni or elector_legajo
        nombre = f"{fila['nombres']} {fila['apellidos']}"
        if elector is None:
            elector = Elector.objects.create(dni=fila["dni"], legajo=fila["legajo"], nombre=nombre, correo_electronico=fila["mail"])
        else:
            elector.nombre, elector.correo_electronico = nombre, fila["mail"]
            elector.save(update_fields=("nombre", "correo_electronico"))
        configuracion = configuraciones[fila["departamento"].casefold()]
        registro, creada = RegistroPadron.objects.get_or_create(
            elector=elector,
            eleccion=importacion.eleccion,
            defaults={"eleccion_claustro_departamento": configuracion, "sede": sedes[fila["sede"].casefold()]},
        )
        if not creada and registro.eleccion_claustro_departamento_id != configuracion.id:
            raise ValueError("El elector ya figura en esta elección con otro claustro o departamento.")
        if not creada and registro.sede_id != sedes[fila["sede"].casefold()].id:
            registro.sede = sedes[fila["sede"].casefold()]
            registro.save(update_fields=("sede",))
        cantidad_creada += int(creada)
    generar_mesas_automaticas(importacion.eleccion_claustro)
    importacion.estado = ImportacionPadron.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.cantidad_filas = len(resultado.filas)
    importacion.cantidad_validas = len(resultado.filas)
    importacion.cantidad_errores = 0
    importacion.save(update_fields=("estado", "confirmada_en", "cantidad_filas", "cantidad_validas", "cantidad_errores"))
    return cantidad_creada
