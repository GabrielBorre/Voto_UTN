import csv
import hashlib
import io
from collections import defaultdict
from dataclasses import dataclass

from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from openpyxl import load_workbook

from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
)
from apps.padron.models import (
    AsignacionPadronVotacion,
    AsignacionSedePadron,
    ConfiguracionSedesClaustro,
    EmisionPadronImprimible,
    Elector,
    ErrorImportacionPadron,
    ImportacionPadron,
    PadronVotacion,
    RegistroPadron,
    ReglaSedeClaustro,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.auditoria.services import registrar_evento
from apps.parametros.models import Departamento, Sede


# Campos canónicos que el sistema espera para procesar el padrón
CANONICAL_FIELDS = ("dni", "legajo", "nombres", "apellidos", "mail", "departamento")
OPTIONAL_FIELDS = ("tipo_documento", "tiene_discapacidad", "departamento_principal", "sede", "nivel")

# Cabeceras exactas que se muestran en la plantilla CSV descargada desde la UI.
PLANTILLA_PADRON_HEADERS = (
    "DNI",
    "Tipo Documento",
    "Legajo",
    "Nombre",
    "Apellido",
    "Depto/Carrera",
    "Mail",
    "TieneDiscapacidad",
    "Departamento Principal",
    "Sede donde cursa",
    "Nivel",
)

PLANTILLA_PADRON_EJEMPLO = [
    (
        "40123456",
        "DNI",
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
        "DNI",
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
        "DNI",
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
    "tipo documento": "tipo_documento",
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
    "sede donde cursa": "sede",
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
    configuraciones_padron = EleccionClaustroDepartamento.objects.filter(
        eleccion_claustro=eleccion_claustro,
    ).filter(
        Q(departamento__activo=True) | Q(departamento__isnull=True)
    ).select_related("departamento")
    for configuracion in configuraciones_padron:
        departamento = configuracion.departamento
        if departamento is None:
            if eleccion_claustro.organizacion_departamentos == "sin_departamento":
                configuraciones[""] = configuracion
            continue
        configuraciones[departamento.codigo.casefold()] = configuracion
        configuraciones[departamento.nombre.casefold()] = configuracion
    sedes_disponibles = {sede.nombre.casefold() for sede in Sede.objects.filter(activa=True)}
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
            if campo == "tipo_documento" and not valor:
                valor = "DNI"
            fila[campo] = valor
        # Leer campos opcionales si están presentes
        for campo in OPTIONAL_FIELDS:
            original_header = canonical_to_original.get(campo)
            fila[campo] = (fila_original.get(original_header) or "").strip() if original_header is not None else ""
        if not fila["tipo_documento"]:
            fila["tipo_documento"] = "DNI"
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
            errores.append((numero_fila, "departamento", "El departamento no fue habilitado para este claustro o la fila no corresponde a un claustro sin distinción por departamento."))
        if fila.get("sede") and fila["sede"].casefold() not in sedes_disponibles:
            errores.append((numero_fila, "sede", "La sede donde cursa no está registrada o no está activa."))
        if fila.get("nivel"):
            try:
                int(fila["nivel"])
            except ValueError:
                errores.append((numero_fila, "nivel", "Nivel debe ser un número entero."))
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


@transaction.atomic
def calcular_mesas_automaticas_eleccion(eleccion, *, usuario=None, request=None):
    """Calcula y reemplaza, en una sola operaciÃ³n, las mesas de toda la elecciÃ³n."""
    eleccion = Eleccion.objects.select_for_update().get(pk=eleccion.pk)
    if eleccion.estado not in (Eleccion.Estado.BORRADOR, Eleccion.Estado.PREPARADA):
        raise ValueError("Las mesas solo pueden recalcularse antes de abrir la elección.")
    claustros = list(EleccionClaustro.objects.filter(eleccion=eleccion).select_related("claustro").order_by("id"))
    if not claustros:
        raise ValueError("La elecciÃ³n no tiene claustros configurados.")

    errores = []
    for claustro in claustros:
        if not claustro.maximo_votantes_por_mesa or claustro.maximo_votantes_por_mesa < 1:
            errores.append(f"{claustro.claustro}: falta configurar un mÃ¡ximo de electores por mesa.")

    registros = list(
        RegistroPadron.objects.filter(eleccion=eleccion, activo=True)
        .select_related(
            "elector",
            "eleccion_claustro_departamento__eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
        )
        .order_by(
            "eleccion_claustro_departamento__eleccion_claustro_id",
            "eleccion_claustro_departamento__departamento__nombre",
            "elector__apellido",
            "elector__nombre",
            "elector__legajo",
        )
    )
    claustros_con_electores = {
        registro.eleccion_claustro_departamento.eleccion_claustro_id
        for registro in registros
    }
    errores = []
    for claustro in claustros:
        if (
            claustro.id in claustros_con_electores
            and (not claustro.maximo_votantes_por_mesa or claustro.maximo_votantes_por_mesa < 1)
        ):
            errores.append(f"{claustro.claustro}: falta configurar el máximo de electores por mesa.")

    registro_ids = [registro.id for registro in registros]
    asignaciones_sede = {
        asignacion.registro_padron_id: asignacion
        for asignacion in AsignacionSedePadron.objects.filter(
            registro_padron_id__in=registro_ids,
        ).select_related("sede")
    }
    grupos = defaultdict(list)
    for registro in registros:
        asignacion = asignaciones_sede.get(registro.id)
        claustro = registro.eleccion_claustro_departamento.eleccion_claustro
        if asignacion is None or asignacion.estado != AsignacionSedePadron.Estado.ASIGNADA or not asignacion.sede_id:
            errores.append(f"{claustro.claustro}: hay electores sin sede electoral asignada.")
            continue
        if not asignacion.sede.activa or not EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento=registro.eleccion_claustro_departamento,
            sede_id=asignacion.sede_id,
        ).exists():
            errores.append(f"{claustro.claustro}: hay asignaciones a sedes no habilitadas para su alcance.")
            continue
        grupos[(claustro, registro.eleccion_claustro_departamento, asignacion.sede)].append(registro)

    if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
        errores.append("Ya se emitieron QR para esta elecciÃ³n; no se pueden recalcular sus mesas.")

    mesas_anteriores = Mesa.objects.filter(eleccion=eleccion, generada_automaticamente=True)
    if mesas_anteriores.filter(Q(participaciones__isnull=False) | Q(autoridades__isnull=False)).exists():
        errores.append("Hay mesas automÃ¡ticas vinculadas a participaciones o autoridades y no se pueden reemplazar.")
    if AsignacionMesa.objects.filter(
        registro_padron_id__in=registro_ids,
        mesa__eleccion=eleccion,
        mesa__generada_automaticamente=False,
    ).exists():
        errores.append("Hay electores del padrÃ³n asignados a mesas manuales; deben revisarse antes del cÃ¡lculo automÃ¡tico.")

    if errores:
        raise ValueError("No se modificÃ³ ninguna mesa. RevisÃ¡: " + " ".join(dict.fromkeys(errores)))

    maximo_por_claustro = {
        claustro.id: claustro.maximo_votantes_por_mesa
        for claustro in claustros
        if claustro.id in claustros_con_electores
    }
    ultimo_numero = Mesa.objects.filter(
        eleccion=eleccion,
        generada_automaticamente=False,
    ).aggregate(ultimo=Max("numero"))["ultimo"] or 0
    mesas_nuevas = []
    asignaciones_nuevas = []
    resumen = defaultdict(lambda: {"electores": 0, "mesas": 0})
    distribuciones = {
        grupo: _distribucion_electores_por_mesa(len(electores), maximo_por_claustro[grupo[0].id])
        for grupo, electores in grupos.items()
    }
    for (claustro, alcance, sede), electores in grupos.items():
        for cantidad in distribuciones[(claustro, alcance, sede)]:
            ultimo_numero += 1
            mesa = Mesa(
                eleccion=eleccion,
                numero=ultimo_numero,
                eleccion_claustro_departamento=alcance,
                sede=sede,
                generada_automaticamente=True,
            )
            mesa.clean()
            mesas_nuevas.append(mesa)
            resumen[claustro.claustro.nombre]["mesas"] += 1
            resumen[claustro.claustro.nombre]["electores"] += cantidad

    cantidad_mesas_anteriores = mesas_anteriores.count()
    AsignacionMesa.objects.filter(mesa__in=mesas_anteriores).delete()
    mesas_anteriores.delete()
    Mesa.objects.bulk_create(mesas_nuevas)

    indice_mesa = 0
    for (claustro, _alcance, _sede), electores in grupos.items():
        inicio = 0
        for cantidad in distribuciones[(claustro, _alcance, _sede)]:
            mesa = mesas_nuevas[indice_mesa]
            indice_mesa += 1
            asignaciones_nuevas.extend(
                AsignacionMesa(registro_padron=registro, mesa=mesa)
                for registro in electores[inicio:inicio + cantidad]
            )
            inicio += cantidad
    AsignacionMesa.objects.bulk_create(asignaciones_nuevas)

    registrar_evento(
        accion="padron.mesas_automaticas_recalculadas",
        entidad="Eleccion",
        entidad_id=eleccion.pk,
        eleccion=eleccion,
        usuario=usuario,
        request=request,
        datos_anteriores={"mesas_automaticas": cantidad_mesas_anteriores},
        datos_nuevos={
            "mesas_automaticas": len(mesas_nuevas),
            "electores_asignados": len(asignaciones_nuevas),
            "claustros": dict(resumen),
        },
    )
    return {"mesas": len(mesas_nuevas), "electores": len(asignaciones_nuevas), "claustros": dict(resumen)}


def _distribucion_electores_por_mesa(cantidad_electores, maximo_por_mesa):
    """Mantiene llenas las mesas previas y reparte el remanente entre las dos últimas."""
    cantidad_mesas = (cantidad_electores + maximo_por_mesa - 1) // maximo_por_mesa
    if cantidad_mesas <= 1:
        return [cantidad_electores]

    cantidad_mesas_llenas = max(0, cantidad_mesas - 2)
    distribucion = [maximo_por_mesa] * cantidad_mesas_llenas
    remanente = cantidad_electores - (cantidad_mesas_llenas * maximo_por_mesa)
    mitad_superior = (remanente + 1) // 2
    mitad_inferior = remanente // 2
    return distribucion + [mitad_superior, mitad_inferior]


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
                tipo_documento=fila["tipo_documento"],
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
            elector.tipo_documento = fila["tipo_documento"]
            elector.apellido = fila["apellidos"]
            elector.correo_electronico = fila["mail"]
            # actualizar discapacidad y departamento principal si cambian
            updated_fields = ["nombre", "apellido", "tipo_documento", "correo_electronico"]
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
                "sede": sedes.get(fila.get("sede", "").casefold()),
                "nivel": fila.get("nivel", ""),
            },
        )
        if not creada and registro.eleccion_claustro_departamento_id != configuracion.id:
            raise ValueError("El elector ya figura en esta elección con otro claustro o departamento.")
        sede_donde_cursa = sedes.get(fila.get("sede", "").casefold())
        if not creada and registro.sede_id != (sede_donde_cursa.id if sede_donde_cursa else None):
            registro.sede = sede_donde_cursa
            registro.save(update_fields=("sede",))
        # actualizar nivel si cambia
        nivel_csv = fila.get("nivel", "")
        if not creada and registro.nivel != nivel_csv:
            registro.nivel = nivel_csv
            registro.save(update_fields=("nivel",))
        cantidad_creada += int(creada)
    invalidar_calculo_padrones_votacion(importacion.eleccion_claustro)
    importacion.estado = ImportacionPadron.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.cantidad_filas = len(resultado.filas)
    importacion.cantidad_validas = len(resultado.filas)
    importacion.cantidad_errores = 0
    importacion.save(update_fields=("estado", "confirmada_en", "cantidad_filas", "cantidad_validas", "cantidad_errores"))
    return cantidad_creada


def invalidar_calculo_padrones_votacion(eleccion_claustro):
    padrones = PadronVotacion.objects.filter(eleccion_claustro=eleccion_claustro)
    AsignacionPadronVotacion.objects.filter(padron_votacion__in=padrones).delete()
    padrones.update(calculado_en=None)
    invalidar_asignaciones_sede_claustro(eleccion_claustro)


def claustro_tiene_emision_vigente(eleccion_claustro):
    return EmisionPadronImprimible.objects.filter(
        eleccion_claustro=eleccion_claustro,
        estado=EmisionPadronImprimible.Estado.VIGENTE,
    ).exists() or RegistroPadron.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        qr_generado_en__isnull=False,
    ).exists()


@transaction.atomic
def registrar_emision_padron_imprimible(eleccion, usuario):
    ahora = timezone.now()
    clausuros_emitidos = []
    for claustro in eleccion.elecciones_claustro.all():
        registros = RegistroPadron.objects.filter(
            eleccion=eleccion,
            eleccion_claustro_departamento__eleccion_claustro=claustro,
            activo=True,
            asignacion_mesa__isnull=False,
        ).select_related("asignacion_mesa__mesa")
        if not registros.exists():
            continue
        EmisionPadronImprimible.objects.get_or_create(
            eleccion_claustro=claustro,
            estado=EmisionPadronImprimible.Estado.VIGENTE,
            defaults={"emitida_por": usuario},
        )
        for registro in registros:
            RegistroPadron.objects.filter(pk=registro.pk).update(
                qr_generado_en=ahora,
                numero_mesa_qr=registro.asignacion_mesa.mesa.numero,
            )
        clausuros_emitidos.append(claustro)
        registrar_evento(
            accion="padron.imprimible_emitido",
            entidad="EleccionClaustro",
            entidad_id=claustro.id,
            eleccion=eleccion,
            usuario=usuario,
            datos_nuevos={"cantidad_registros": registros.count()},
        )
    return clausuros_emitidos


@transaction.atomic
def rehabilitar_cambios_padron(eleccion_claustro, usuario):
    ahora = timezone.now()
    emisiones = EmisionPadronImprimible.objects.select_for_update().filter(
        eleccion_claustro=eleccion_claustro,
        estado=EmisionPadronImprimible.Estado.VIGENTE,
    )
    emisiones.update(
        estado=EmisionPadronImprimible.Estado.INVALIDADA,
        invalidada_en=ahora,
        invalidada_por=usuario,
        motivo_invalidacion="Se rehabilitaron cambios de configuración del claustro.",
    )
    registros = RegistroPadron.objects.select_for_update().filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    )
    for registro in registros:
        registro.identificador_qr = ""
        registro.qr_generado_en = None
        registro.numero_mesa_qr = None
        registro.save(update_fields=("identificador_qr", "qr_generado_en", "numero_mesa_qr"))
    registrar_evento(
        accion="padron.emision_invalidada",
        entidad="EleccionClaustro",
        entidad_id=eleccion_claustro.id,
        eleccion=eleccion_claustro.eleccion,
        usuario=usuario,
        datos_nuevos={"cantidad_registros": registros.count()},
    )


def _valor_condicion(registro, campo):
    if campo == "departamento":
        departamento = registro.eleccion_claustro_departamento.departamento
        return departamento.codigo if departamento else ""
    if campo == "departamento_principal":
        departamento = registro.elector.departamento_principal
        return departamento.codigo if departamento else ""
    if campo == "nivel":
        return registro.nivel
    if campo == "sede_donde_cursa":
        return registro.sede.nombre if registro.sede_id else ""
    if campo == "discapacidad":
        return "si" if registro.elector.tiene_discapacidad else "no"
    return ""


def coincide_condicion(registro, condicion):
    actual = _valor_condicion(registro, condicion.campo)
    if condicion.campo == "nivel":
        try:
            actual = int(actual)
        except (TypeError, ValueError):
            return False
        esperado = int(condicion.valor)
        return {
            "igual": actual == esperado,
            "mayor": actual > esperado,
            "mayor_igual": actual >= esperado,
            "menor": actual < esperado,
            "menor_igual": actual <= esperado,
        }[condicion.operador]
    actual = str(actual).casefold()
    valores = {valor.strip().casefold() for valor in condicion.valor.split(",") if valor.strip()}
    return actual in valores


def alcances_con_sedes_multiples(eleccion_claustro):
    """Alcances con más de una sede activa habilitada para el claustro."""
    return EleccionClaustroDepartamento.objects.filter(
        eleccion_claustro=eleccion_claustro,
    ).annotate(
        cantidad_sedes_activas=Count(
            "sedes_habilitadas",
            filter=Q(sedes_habilitadas__sede__activa=True),
            distinct=True,
        ),
    ).filter(cantidad_sedes_activas__gt=1).select_related("departamento")


def invalidar_asignaciones_sede_claustro(eleccion_claustro):
    AsignacionSedePadron.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).delete()


def estado_eliminacion_padron_claustro(eleccion_claustro):
    """Devuelve el resumen y los bloqueos para vaciar el padrón del claustro."""
    from apps.asistencia.models import RegistroParticipacion
    from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
    from apps.justificativos.models import JustificativoAusencia
    from apps.partidos.models import Candidato

    registros = RegistroPadron.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    )
    identificadores = registros.values_list("id", flat=True)
    identificadores_electores = registros.values_list("elector_id", flat=True)
    cantidad_registros = registros.count()
    cantidad_electores = registros.values("elector_id").distinct().count()
    electores_conservados = Elector.objects.filter(pk__in=identificadores_electores).filter(
        Q(registros_padron__eleccion_id__in=RegistroPadron.objects.exclude(
            eleccion_id=eleccion_claustro.eleccion_id,
        ).values_list("eleccion_id", flat=True))
        | Q(candidaturas__isnull=False)
        | Q(perfil_usuario__isnull=False)
    ).values("id").distinct().count()
    bloqueos = []

    if eleccion_claustro.eleccion.estado not in (
        eleccion_claustro.eleccion.Estado.BORRADOR,
        eleccion_claustro.eleccion.Estado.PREPARADA,
    ):
        bloqueos.append("La elección está abierta o cerrada; no se puede vaciar el padrón.")
    emision_vigente = cantidad_registros > 0 and claustro_tiene_emision_vigente(eleccion_claustro)
    if emision_vigente:
        bloqueos.append(
            "Hay un padrón imprimible o QR emitidos. Primero rehabilitá los cambios para invalidar esa emisión."
        )

    dependencias = (
        ("participaciones", "participaciones registradas", RegistroParticipacion.objects.filter(registro_padron_id__in=identificadores).count()),
        ("justificativos", "justificativos asociados", JustificativoAusencia.objects.filter(registro_padron_id__in=identificadores).count()),
        ("candidaturas de autoridad", "candidaturas de autoridad", CandidaturaAutoridad.objects.filter(registro_padron_id__in=identificadores).count()),
        ("asignaciones de autoridad", "asignaciones de autoridad", AsignacionAutoridad.objects.filter(registro_padron_id__in=identificadores).count()),
        ("preferencias de autoridad", "preferencias de autoridad", PreferenciaAutoridad.objects.filter(registro_padron_id__in=identificadores).count()),
        (
            "candidaturas electorales",
            "candidaturas en listas de esta elección",
            Candidato.objects.filter(
                elector_id__in=registros.values_list("elector_id", flat=True),
                lista__participacion__eleccion=eleccion_claustro.eleccion,
            ).count(),
        ),
    )
    for _clave, descripcion, cantidad in dependencias:
        if cantidad:
            bloqueos.append(f"Hay {cantidad} {descripcion}; resolvelas antes de eliminar el padrón.")

    return {
        "cantidad_registros": cantidad_registros,
        "cantidad_electores": cantidad_electores,
        "cantidad_electores_a_conservar": electores_conservados,
        "cantidad_electores_a_eliminar": cantidad_electores - electores_conservados,
        "cantidad_mesas_automaticas": Mesa.objects.filter(
            eleccion=eleccion_claustro.eleccion,
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            generada_automaticamente=True,
        ).count(),
        "emision_vigente": emision_vigente,
        "bloqueos": bloqueos,
    }


@transaction.atomic
def eliminar_padron_claustro(eleccion_claustro, usuario, request=None):
    """Vacía los registros de padrón de un claustro y conserva su historial."""
    eleccion_claustro = type(eleccion_claustro).objects.select_for_update().select_related(
        "eleccion",
        "claustro",
    ).get(pk=eleccion_claustro.pk)
    resumen = estado_eliminacion_padron_claustro(eleccion_claustro)
    if resumen["bloqueos"]:
        raise ValueError(" ".join(resumen["bloqueos"]))
    if not resumen["cantidad_registros"]:
        raise ValueError("Este claustro no tiene registros de padrón para eliminar.")

    registros = RegistroPadron.objects.select_for_update().filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    )
    registro_ids = list(registros.values_list("id", flat=True))
    elector_ids = list(set(registros.values_list("elector_id", flat=True)))
    mesas_automaticas = Mesa.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        generada_automaticamente=True,
    )

    # Son resultados calculados, no historial electoral; se limpian al vaciar el padrón.
    AsignacionMesa.objects.filter(registro_padron_id__in=registro_ids).delete()
    AsignacionPadronVotacion.objects.filter(registro_padron_id__in=registro_ids).delete()
    PadronVotacion.objects.filter(eleccion_claustro=eleccion_claustro).update(calculado_en=None)
    cantidad_eliminada = resumen["cantidad_registros"]
    registros.delete()
    electores_sin_referencias = Elector.objects.filter(
        pk__in=elector_ids,
        registros_padron__isnull=True,
        candidaturas__isnull=True,
        perfil_usuario__isnull=True,
    )
    cantidad_electores_eliminados = electores_sin_referencias.count()
    electores_sin_referencias.delete()
    importaciones_marcadas = ImportacionPadron.objects.filter(
        eleccion_claustro=eleccion_claustro,
        estado=ImportacionPadron.Estado.CONFIRMADA,
    ).update(estado=ImportacionPadron.Estado.PADRON_ELIMINADO)
    mesas_automaticas.filter(
        asignaciones_padron__isnull=True,
        participaciones__isnull=True,
        autoridades__isnull=True,
    ).delete()

    registrar_evento(
        accion="padron.claustro_vaciado",
        entidad="EleccionClaustro",
        entidad_id=eleccion_claustro.pk,
        eleccion=eleccion_claustro.eleccion,
        usuario=usuario,
        request=request,
        datos_anteriores={
            "registros": resumen["cantidad_registros"],
            "electores": resumen["cantidad_electores"],
            "electores_huerfanos_eliminados": cantidad_electores_eliminados,
            "mesas_automaticas": resumen["cantidad_mesas_automaticas"],
            "importaciones_confirmadas": importaciones_marcadas,
        },
        datos_nuevos={
            "registros_eliminados": cantidad_eliminada,
            "electores_conservados": resumen["cantidad_electores_a_conservar"],
            "electores_huerfanos_eliminados": cantidad_electores_eliminados,
            "importaciones_marcadas_como_padron_eliminado": importaciones_marcadas,
            "historial_importaciones_conservado": True,
        },
    )
    return resumen


def registro_habilitado_para_puesto(registro, puesto):
    return (
        puesto.eleccion_claustro_id == registro.eleccion_claustro_departamento.eleccion_claustro_id
        and (puesto.eleccion_claustro_departamento_id is None or puesto.eleccion_claustro_departamento_id == registro.eleccion_claustro_departamento_id)
    )


def registro_incluido_en_padron(registro, padron):
    grupos = list(padron.grupos_inclusion.prefetch_related("condiciones"))
    if not grupos:
        return False
    puestos = [relacion.puesto_eleccion for relacion in padron.puestos_configurados.select_related("puesto_eleccion")]
    if not puestos or not all(registro_habilitado_para_puesto(registro, puesto) for puesto in puestos):
        return False
    return any(all(coincide_condicion(registro, condicion) for condicion in grupo.condiciones.all()) for grupo in grupos)


@transaction.atomic
def calcular_padrones_votacion(eleccion_claustro):
    padrones = list(PadronVotacion.objects.filter(eleccion_claustro=eleccion_claustro).prefetch_related(
        "puestos_configurados__puesto_eleccion",
        "grupos_inclusion__condiciones",
        "configuraciones_sede__reglas",
    ))
    registros = list(RegistroPadron.objects.filter(
        eleccion=eleccion_claustro.eleccion,
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        activo=True,
    ).select_related("elector__departamento_principal", "sede", "eleccion_claustro_departamento__departamento"))

    candidatos = []
    cargos_por_registro = defaultdict(set)
    for padron in padrones:
        puestos = [relacion.puesto_eleccion for relacion in padron.puestos_configurados.select_related("puesto_eleccion")]
        for registro in registros:
            if not registro_incluido_en_padron(registro, padron):
                continue
            repetidos = cargos_por_registro[registro.id].intersection({puesto.id for puesto in puestos})
            if repetidos:
                raise ValueError(f"{registro.elector.nombre_completo} recibiría el mismo cargo en más de un padrón de votación.")
            cargos_por_registro[registro.id].update(puesto.id for puesto in puestos)
            configuracion = next((item for item in padron.configuraciones_sede.all() if item.eleccion_claustro_departamento_id == registro.eleccion_claustro_departamento_id), None)
            if configuracion is None:
                raise ValueError(f"Falta la sede predeterminada para {registro.eleccion_claustro_departamento.departamento} en «{padron.nombre}».")
            reglas = sorted(configuracion.reglas.all(), key=lambda regla: (regla.orden, regla.id))
            sede = next((regla.sede_destino for regla in reglas if coincide_condicion(registro, regla)), configuracion.sede_predeterminada)
            candidatos.append(AsignacionPadronVotacion(padron_votacion=padron, registro_padron=registro, sede_asignada=sede))

    AsignacionPadronVotacion.objects.filter(padron_votacion__in=padrones).delete()
    AsignacionPadronVotacion.objects.bulk_create(candidatos)
    ahora = timezone.now()
    PadronVotacion.objects.filter(pk__in=[padron.pk for padron in padrones]).update(calculado_en=ahora)
    return len(candidatos)


@transaction.atomic
def calcular_asignaciones_sede_claustro(eleccion_claustro):
    """Asigna una sede por elector, independientemente de sus puestos o listas."""
    configuracion, _ = ConfiguracionSedesClaustro.objects.get_or_create(
        eleccion_claustro=eleccion_claustro,
    )
    reglas = list(configuracion.reglas.prefetch_related("alcances_especificos").order_by("orden", "id"))
    sedes_por_alcance = defaultdict(set)
    for alcance_id, sede_id in EleccionClaustroDepartamentoSede.objects.filter(
        eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        sede__activa=True,
    ).values_list("eleccion_claustro_departamento_id", "sede_id"):
        sedes_por_alcance[alcance_id].add(sede_id)
    alcances_por_regla = {
        regla.id: set(regla.alcances_especificos.values_list("id", flat=True))
        for regla in reglas
        if not regla.aplicar_a_todos
    }
    registros = list(
        RegistroPadron.objects.filter(
            eleccion=eleccion_claustro.eleccion,
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            activo=True,
        ).select_related(
            "elector__departamento_principal",
            "sede",
            "eleccion_claustro_departamento__departamento",
        )
    )

    asignaciones = []
    pendientes = 0
    for registro in registros:
        alcance = registro.eleccion_claustro_departamento
        sede_ids = sedes_por_alcance[alcance.id]
        sede_elegida = None
        regla_aplicada = None

        if len(sede_ids) == 1:
            sede_elegida = Sede.objects.get(pk=next(iter(sede_ids)))
        elif len(sede_ids) > 1:
            for regla in reglas:
                if regla.sede_destino_id not in sede_ids:
                    # La regla no participa para este alcance si el destino
                    # no está habilitado allí; se prueba la regla siguiente.
                    continue
                if not regla.aplicar_a_todos and alcance.id not in alcances_por_regla[regla.id]:
                    continue
                if coincide_condicion(registro, regla):
                    sede_elegida = regla.sede_destino
                    regla_aplicada = regla
                    break

        estado = AsignacionSedePadron.Estado.ASIGNADA if sede_elegida else AsignacionSedePadron.Estado.PENDIENTE
        pendientes += int(estado == AsignacionSedePadron.Estado.PENDIENTE)
        asignaciones.append(
            AsignacionSedePadron(
                registro_padron=registro,
                sede=sede_elegida,
                regla_aplicada=regla_aplicada,
                estado=estado,
            )
        )

    AsignacionSedePadron.objects.filter(
        registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
    ).delete()
    AsignacionSedePadron.objects.bulk_create(asignaciones)
    return {"asignadas": len(asignaciones) - pendientes, "pendientes": pendientes}
