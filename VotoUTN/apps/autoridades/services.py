import csv
import io

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron


PLANTILLA_AUTORIDADES_HEADERS = (
    "DNI",
    "Legajo",
    "Nombre",
    "Apellido",
    "Depto/Carrera",
    "Mail",
)
PLANTILLA_AUTORIDADES_EJEMPLO = [
    ("40123456", "2024001", "Juan", "Perez", "K", "juan.perez@utn.edu.ar"),
    ("40234567", "2024002", "Maria", "Garcia", "K", "maria.garcia@utn.edu.ar"),
]

CANONICAL_FIELDS = ("dni", "legajo", "nombre", "apellido", "departamento", "mail")
HEADER_VARIANTS_TO_CANONICAL = {
    "dni": "dni",
    "documento": "dni",
    "documento_nro": "dni",
    "legajo": "legajo",
    "nombre": "nombre",
    "nombres": "nombre",
    "apellido": "apellido",
    "apellidos": "apellido",
    "depto/carrera": "departamento",
    "departamento": "departamento",
    "departamento principal": "departamento",
    "mail": "mail",
    "correo": "mail",
    "correo electronico": "mail",
    "mai": "mail",
}
CARACTERES_FORMULA = ("=", "+", "-", "@")


def leer_filas_autoridades(contenido: bytes, nombre_archivo: str = "") -> list[dict[str, str]]:
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
    except UnicodeDecodeError as exc:
        raise ValueError("El archivo debe estar codificado en UTF-8.") from exc

    lector = csv.DictReader(io.StringIO(texto, newline=""))
    filas = []
    for fila in lector:
        if not fila:
            continue
        filas.append({(clave or "").strip(): (valor or "").strip() for clave, valor in fila.items()})
    return filas


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
    if creada:
        from apps.usuarios.models import AsignacionRol, PerfilUsuario

        perfil = PerfilUsuario.objects.filter(elector=registro_padron.elector, activo=True).select_related("usuario").first()
        if perfil is None:
            Usuario = get_user_model()
            base = f"autoridad-{registro_padron.elector.legajo}"
            nombre_usuario = base
            indice = 1
            while Usuario.objects.filter(username=nombre_usuario).exists():
                indice += 1
                nombre_usuario = f"{base}-{indice}"
            usuario_autoridad = Usuario(username=nombre_usuario, email=registro_padron.elector.correo_electronico)
            usuario_autoridad.set_unusable_password()
            usuario_autoridad.save()
            perfil = PerfilUsuario.objects.create(usuario=usuario_autoridad, elector=registro_padron.elector)
        if perfil:
            AsignacionRol.objects.get_or_create(
                usuario=perfil.usuario,
                rol=AsignacionRol.Rol.AUTORIDAD_MESA,
                eleccion=registro_padron.eleccion,
                sede=mesa.sede,
                mesa=mesa,
            )
    return asignacion, creada


def validar_csv_autoridades(contenido, eleccion):
    try:
        filas = leer_filas_autoridades(contenido)
    except ValueError as error:
        return [], [(None, str(error))]

    if not filas:
        return [], [(None, "El archivo no contiene filas de autoridades.")]

    fieldnames = list(filas[0].keys())
    normalized_to_original = {(str(cabecera or "").strip().lower()): cabecera for cabecera in fieldnames}
    canonical_to_original = {}
    for normalized, original in normalized_to_original.items():
        mapped = HEADER_VARIANTS_TO_CANONICAL.get(normalized)
        if mapped:
            canonical_to_original.setdefault(mapped, original)

    missing = [campo for campo in CANONICAL_FIELDS if campo not in canonical_to_original]
    if missing:
        return [], [(None, f"Las cabeceras deben incluir: {', '.join(CANONICAL_FIELDS)}.")]

    filas_normales = []
    errores = []
    vistos = set()
    for numero, fila_original in enumerate(filas, start=2):
        fila = {}
        for campo in CANONICAL_FIELDS:
            original_header = canonical_to_original.get(campo)
            fila[campo] = (fila_original.get(original_header) or "").strip() if original_header is not None else ""
        filas_normales.append(fila)

        clave = (fila["dni"], fila["legajo"])
        if clave in vistos:
            errores.append((numero, "El elector esta repetido en el archivo."))
        vistos.add(clave)

        for campo, valor in fila.items():
            if valor.startswith(CARACTERES_FORMULA):
                errores.append((numero, f"El valor de {campo} no es valido."))

        if not fila["dni"].isdigit() or not 7 <= len(fila["dni"]) <= 12:
            errores.append((numero, "El DNI debe contener entre 7 y 12 digitos."))
        if not fila["legajo"]:
            errores.append((numero, "El legajo es obligatorio."))
        if not fila["nombre"] or not fila["apellido"]:
            errores.append((numero, "Nombre y apellido son obligatorios."))
        try:
            validate_email(fila["mail"])
        except Exception:
            errores.append((numero, "El correo electronico no tiene un formato valido."))

        if not fila["departamento"]:
            errores.append((numero, "El departamento es obligatorio."))

        padron = RegistroPadron.objects.filter(
            eleccion=eleccion,
            elector__dni=fila["dni"],
            elector__legajo=fila["legajo"],
            activo=True,
        ).select_related("elector", "eleccion_claustro_departamento__departamento").first()

        if padron is None:
            errores.append((numero, "El elector no pertenece al padron activo de esta eleccion."))
            continue

        departamento = padron.eleccion_claustro_departamento.departamento
        if fila["departamento"].casefold() not in {departamento.codigo.casefold(), departamento.nombre.casefold()}:
            errores.append((numero, "El departamento no coincide con el padrón del elector en esta eleccion."))

    return filas_normales, errores


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
