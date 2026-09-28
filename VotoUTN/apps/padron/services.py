import csv
import hashlib
import io
from collections import defaultdict
from dataclasses import dataclass

from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from openpyxl import load_workbook

from apps.elecciones.models import (
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, ErrorImportacionPadron, ImportacionPadron, RegistroPadron
from apps.parametros.models import Departamento, Sede


# Campos canónicos que el sistema espera para procesar el padrón
CANONICAL_FIELDS = ("dni", "legajo", "nombres", "apellidos", "mail", "departamento", "sede")
OPTIONAL_FIELDS = ("tiene_discapacidad", "departamento_principal", "nivel")

# Cabeceras exactas que se muestran en la plantilla CSV descargada desde la UI.
PLANTILLA_PADRON_HEADERS = (
    "DNI",
    "Legajo",
    "Nombre",
    "Apellido",
    "Depto/Carrera",
    "Mail",
    "TieneDiscapacidad",
    "Departamento Principal",
    "Sede donde asiste",
    "Nivel",
)

PLANTILLA_PADRON_EJEMPLO = [
    (
        "40123456",
        "2024001",
        "Juan",
        "Perez",
        "K",
        "juan.perez@frba.utn.edu.ar",
        "Si",
        "K",
        "Campus",
        "1",
    ),
    (
        "40234567",
        "2024002",
        "Maria",
        "Garcia",
        "K",
        "maria.garcia@frba.utn.edu.ar",
        "No",
        "K",
        "Campus",
        "1",
    ),
    (
        "40345678",
        "2024003",
        "Carlos",
        "Lopez",
        "K",
        "carlos.lopez@frba.utn.edu.ar",
        "Si",
        "K",
        "Campus",
        "2",
    ),
]

# Mapeo de variantes de cabeceras (normalizadas: lower().strip()) -> campo canónico
# Soporta el formato antiguo y el nuevo solicitado (ej. 'Nombre' -> 'nombres',
# 'Depto/Carrera' y 'Departamento Principal' -> 'departamento',
# 'Sede donde asiste' -> 'sede').
HEADER_VARIANTS_TO_CANONICAL = {
    "dni": "dni",
    "legajo": "legajo",
    "nombres": "nombres",
    "nombre": "nombres",
    "apellidos": "apellidos",
    "apellido": "apellidos",
    "mail": "mail",
    "correo": "mail",
    "correo electronico": "mail",
    "depto/carrera": "departamento",
    "departamento": "departamento",
    "departamento principal": "departamento_principal",
    "sede": "sede",
    "sede donde asiste": "sede",
    "tienediscapacidad": "tiene_discapacidad",
    "tiene discapacidad": "tiene_discapacidad",
    "nivel": "nivel",
}

CARACTERES_FORMULA = ("=", "+", "-", "@")
DOMINIO_EMAIL_INSTITUCIONAL = "frba.utn.edu.ar"


def normalizar_identificador_numerico(valor: str) -> str:
    valor = (valor or "").strip()
    if not valor:
        return ""
    if "." in valor:
        try:
            numero = float(valor)
        except ValueError:
            return valor
        if numero.is_integer():
            return str(int(numero))
    return valor


@dataclass
class ResultadoValidacion:
    filas: list[dict[str, str]]
    errores: list[tuple[int | None, str, str]]


def leer_filas_padron(contenido: bytes, nombre_archivo: str = "") -> list[dict[str, str]]:
    nombre_archivo = (nombre_archivo or "").lower()
    if nombre_archivo.endswith((".xlsx", ".xls")):
        libro = load_workbook(filename=io.BytesIO(contenido), read_only=True, data_only=True)
        hoja = libro.active
        filas = list(hoja.iter_rows(values_only=True))
        if not filas:
            return []
        encabezados = [(valor or "").strip() for valor in filas[0]]
        registros = []
        for fila in filas[1:]:
            if not any((valor is not None and str(valor).strip()) for valor in fila):
                continue
            registro = {}
            for indice, nombre_columna in enumerate(encabezados):
                valor = fila[indice] if indice < len(fila) else ""
                registro[nombre_columna] = "" if valor is None else str(valor).strip()
            registros.append(registro)
        return registros

    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("El archivo debe estar codificado en UTF-8.")

    lector = csv.DictReader(io.StringIO(texto, newline=""))
    filas = []
    for fila in lector:
        if not fila:
            continue
        filas.append({(clave or "").strip(): (valor or "").strip() for clave, valor in fila.items()})
    return filas


def detectar_columnas_archivo(contenido: bytes, nombre_archivo: str = "") -> list[str]:
    try:
        filas = leer_filas_padron(contenido, nombre_archivo)
    except ValueError:
        return []
    if not filas:
        return []
    return [str(columna).strip() for columna in filas[0].keys() if str(columna).strip()]


def validar_csv_padron(contenido: bytes, eleccion_claustro, nombre_archivo: str = "") -> ResultadoValidacion:
    try:
        filas = leer_filas_padron(contenido, nombre_archivo)
    except ValueError as error:
        return ResultadoValidacion([], [(None, "archivo", str(error))])

    if not filas:
        return ResultadoValidacion([], [(None, "archivo", "El archivo no contiene filas de padron.")])

    fieldnames = list(filas[0].keys())
    normalized_to_original = {(h or "").strip().lower(): h for h in fieldnames}

    # Construir mapeo canonical -> header original presente en el archivo
    canonical_to_original = {}
    for normalized, original in normalized_to_original.items():
        mapped = HEADER_VARIANTS_TO_CANONICAL.get(normalized)
        if mapped:
            # Si ya hay una cabecera que mapea al mismo canónico, preferimos la primera encontrada
            canonical_to_original.setdefault(mapped, original)

    missing = [c for c in CANONICAL_FIELDS if c not in canonical_to_original]
    if missing:
        return ResultadoValidacion([], [(None, "archivo", f"Las cabeceras deben incluir: {', '.join(CANONICAL_FIELDS)}. Archivo tiene: {', '.join(fieldnames)}")])

    configuraciones = {}
    for configuracion in EleccionClaustroDepartamento.objects.filter(
        eleccion_claustro=eleccion_claustro,
        departamento__activo=True,
    ).select_related("departamento"):
        departamento = configuracion.departamento
        configuraciones[departamento.codigo.casefold()] = configuracion
        configuraciones[departamento.nombre.casefold()] = configuracion
    sedes_permitidas = {
        (habilitacion.eleccion_claustro_departamento_id, habilitacion.sede.nombre.casefold())
        for habilitacion in EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            sede__activa=True,
        ).select_related("sede")
    }
    errores = []
    vistos = defaultdict(set)
    for numero_fila, fila_original in enumerate(filas, start=2):
        # Normalizar la fila a los campos canónicos esperados
        fila = {}
        for campo in CANONICAL_FIELDS:
            original_header = canonical_to_original.get(campo)
            valor = (fila_original.get(original_header) or "").strip() if original_header is not None else ""
            if campo in {"dni", "legajo"}:
                valor = normalizar_identificador_numerico(valor)
            fila[campo] = valor
        # Leer campos opcionales si están presentes
        for campo in OPTIONAL_FIELDS:
            original_header = canonical_to_original.get(campo)
            fila[campo] = (fila_original.get(original_header) or "").strip() if original_header is not None else ""
        filas[numero_fila - 2] = fila
        for campo, valor in fila.items():
            if valor.startswith(CARACTERES_FORMULA):
                errores.append((numero_fila, campo, "No se permiten valores que comiencen con caracteres de formula."))
        dni_normalizado = normalizar_identificador_numerico(fila["dni"])
        fila["dni"] = dni_normalizado
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
        else:
            if fila["mail"].rsplit("@", 1)[-1].casefold() != DOMINIO_EMAIL_INSTITUCIONAL:
                errores.append((numero_fila, "mail", f"El correo electronico debe pertenecer al dominio @{DOMINIO_EMAIL_INSTITUCIONAL}."))
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
            if elector_existente:
                if elector_existente.dni != fila["dni"]:
                    errores.append((numero_fila, "dni", "El DNI no coincide con el elector existente."))
                if elector_existente.legajo != fila["legajo"]:
                    errores.append((numero_fila, "legajo", "El legajo no coincide con el elector existente."))
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
    if RegistroPadron.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        qr_generado_en__isnull=False,
    ).exists():
        raise ValueError("No se pueden regenerar las mesas: ya se emitieron códigos QR para este claustro.")
    maximo = eleccion_claustro.maximo_votantes_por_mesa
    if not maximo:
        maximo = 1
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
        "eleccion_claustro_departamento__departamento__nombre", "sede__nombre", "elector__apellido", "elector__nombre", "elector__legajo"
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
    if RegistroPadron.objects.filter(
        eleccion=importacion.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=importacion.eleccion_claustro,
        qr_generado_en__isnull=False,
    ).exists():
        raise ValueError("No se puede confirmar un nuevo padrón: ya se emitieron códigos QR para este claustro.")
    importacion.archivo.open("rb")
    try:
        contenido = importacion.archivo.read()
    finally:
        importacion.archivo.close()
    if hashlib.sha256(contenido).hexdigest() != importacion.huella_archivo:
        raise ValueError("El archivo almacenado no coincide con el archivo previsualizado. Volvé a cargarlo y no lo reemplaces entre la previsualización y la confirmación.")
    resultado = validar_csv_padron(contenido, importacion.eleccion_claustro, importacion.nombre_archivo)
    if resultado.errores:
        registrar_errores(importacion, resultado.errores)
        importacion.cantidad_filas = len(resultado.filas)
        importacion.cantidad_validas = 0
        importacion.cantidad_errores = len(resultado.errores)
        importacion.estado = ImportacionPadron.Estado.RECHAZADA
        importacion.save(update_fields=("cantidad_filas", "cantidad_validas", "cantidad_errores", "estado"))
        detalle = "; ".join(
            f"fila {fila}: {mensaje}" if fila else mensaje
            for fila, _campo, mensaje in resultado.errores[:3]
        )
        if len(resultado.errores) > 3:
            detalle += f"; y {len(resultado.errores) - 3} error(es) más"
        raise ValueError(f"El archivo ya no cumple las validaciones: {detalle}")

    configuraciones = {}
    for configuracion in EleccionClaustroDepartamento.objects.filter(
        eleccion_claustro=importacion.eleccion_claustro,
    ).select_related("departamento"):
        departamento = configuracion.departamento
        configuraciones[departamento.codigo.casefold()] = configuracion
        configuraciones[departamento.nombre.casefold()] = configuracion
    sedes = {sede.nombre.casefold(): sede for sede in Sede.objects.filter(activa=True)}
    cantidad_creada = 0
    for fila in resultado.filas:
        elector_dni = Elector.objects.filter(dni=fila["dni"]).first()
        elector_legajo = Elector.objects.filter(legajo=fila["legajo"]).first()
        if elector_dni and elector_legajo and elector_dni.pk != elector_legajo.pk:
            raise ValueError("El padrón contiene un DNI y un legajo asociados a electores distintos.")
        elector = elector_dni or elector_legajo
        if elector is None:
            elector = Elector.objects.create(
                dni=fila["dni"],
                legajo=fila["legajo"],
                nombre=fila["nombres"],
                apellido=fila["apellidos"],
                correo_electronico=fila["mail"],
                tiene_discapacidad=fila.get("tiene_discapacidad", "").strip().lower() in ("si", "s", "yes", "y", "true", "1"),
            )
            # intentar asignar departamento principal si viene en el CSV
            dept_principal_code = fila.get("departamento_principal") or ""
            if dept_principal_code:
                dept_obj = Departamento.objects.filter(
                    Q(codigo__iexact=dept_principal_code.strip()) | Q(nombre__iexact=dept_principal_code.strip())
                ).first()
                if dept_obj:
                    elector.departamento_principal = dept_obj
                    elector.save(update_fields=("departamento_principal",))
        else:
            elector.nombre = fila["nombres"]
            elector.apellido = fila["apellidos"]
            elector.correo_electronico = fila["mail"]
            # actualizar discapacidad y departamento principal si cambian
            updated_fields = ["nombre", "apellido", "correo_electronico"]
            tiene_disc = fila.get("tiene_discapacidad", "").strip().lower() in ("si", "s", "yes", "y", "true", "1")
            if elector.tiene_discapacidad != tiene_disc:
                elector.tiene_discapacidad = tiene_disc
                updated_fields.append("tiene_discapacidad")
            dept_principal_code = fila.get("departamento_principal") or ""
            if dept_principal_code:
                dept_obj = Departamento.objects.filter(
                    Q(codigo__iexact=dept_principal_code.strip()) | Q(nombre__iexact=dept_principal_code.strip())
                ).first()
                if dept_obj and (elector.departamento_principal_id != dept_obj.id):
                    elector.departamento_principal = dept_obj
                    updated_fields.append("departamento_principal")
            elector.save(update_fields=tuple(updated_fields))
        configuracion = configuraciones[fila["departamento"].casefold()]
        registro, creada = RegistroPadron.objects.get_or_create(
            elector=elector,
            eleccion=importacion.eleccion,
            defaults={
                "eleccion_claustro_departamento": configuracion,
                "sede": sedes[fila["sede"].casefold()],
                "nivel": fila.get("nivel", ""),
            },
        )
        if not creada and registro.eleccion_claustro_departamento_id != configuracion.id:
            raise ValueError("El elector ya figura en esta elección con otro claustro o departamento.")
        if not creada and registro.sede_id != sedes[fila["sede"].casefold()].id:
            registro.sede = sedes[fila["sede"].casefold()]
            registro.save(update_fields=("sede",))
        # actualizar nivel si cambia
        nivel_csv = fila.get("nivel", "")
        if not creada and registro.nivel != nivel_csv:
            registro.nivel = nivel_csv
            registro.save(update_fields=("nivel",))
        cantidad_creada += int(creada)
    generar_mesas_automaticas(importacion.eleccion_claustro)
    importacion.estado = ImportacionPadron.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.cantidad_filas = len(resultado.filas)
    importacion.cantidad_validas = len(resultado.filas)
    importacion.cantidad_errores = 0
    importacion.save(update_fields=("estado", "confirmada_en", "cantidad_filas", "cantidad_validas", "cantidad_errores"))
    return cantidad_creada
