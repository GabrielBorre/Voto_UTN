import csv
import io
import unicodedata
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.partidos.models import Candidato, ImportacionCandidaturas, ListaCandidatos, ParticipacionPartido, PuestoEleccion


ENCABEZADOS_CANDIDATURAS = (
    "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email",
    "claustro", "organo", "puesto", "departamento", "identificador_persona", "dni", "apellido",
    "nombres", "tipo_candidatura", "orden",
)
ENCABEZADOS_OBLIGATORIOS = set(ENCABEZADOS_CANDIDATURAS) - {"apoderado_email", "dni"}


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "").strip())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).casefold().split())


@transaction.atomic
def guardar_con_validacion(formulario, **relaciones):
    instancia = formulario.save(commit=False)
    for nombre, valor in relaciones.items():
        setattr(instancia, nombre, valor)
    instancia.full_clean()
    instancia.save()
    return instancia


def _leer_csv(archivo):
    try:
        contenido = archivo.read().decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValidationError("El archivo debe estar codificado en UTF-8.") from error
    try:
        dialecto = csv.Sniffer().sniff(contenido[:4096], delimiters=";,")
    except csv.Error:
        dialecto = csv.excel
        dialecto.delimiter = ";"
    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    encabezados = {_normalizar(n).replace(" ", "_") for n in (lector.fieldnames or []) if n}
    faltantes = sorted(ENCABEZADOS_OBLIGATORIOS - encabezados)
    if faltantes:
        raise ValidationError(f"Faltan columnas obligatorias: {', '.join(faltantes)}.")
    return lector


def previsualizar_importacion_candidaturas(*, eleccion, archivo, usuario):
    errores, advertencias, filas_validas = [], [], []
    cantidad_total = 0
    try:
        lector = _leer_csv(archivo)
    except ValidationError as error:
        return ImportacionCandidaturas.objects.create(
            eleccion=eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
            estado=ImportacionCandidaturas.Estado.RECHAZADA, errores=error.messages,
        )

    configuraciones = PuestoEleccion.objects.filter(
        eleccion_claustro__eleccion=eleccion, activo=True, puesto__activo=True, puesto__organo__activo=True,
    ).select_related("puesto__organo", "eleccion_claustro__claustro", "eleccion_claustro_departamento__departamento")
    mapa = {}
    for config in configuraciones:
        clave = (
            _normalizar(config.eleccion_claustro.claustro.nombre), _normalizar(config.puesto.organo.nombre),
            _normalizar(config.puesto.nombre),
            _normalizar(config.eleccion_claustro_departamento.departamento.nombre)
            if config.eleccion_claustro_departamento_id else "",
        )
        mapa[clave] = config

    metadatos_presentaciones, espacios = {}, set()
    apariciones_identificador = defaultdict(set)
    for numero_fila, original in enumerate(lector, start=2):
        cantidad_total += 1
        if cantidad_total > 5000:
            errores.append("El archivo supera el máximo de 5000 filas.")
            break
        fila = {_normalizar(k).replace(" ", "_"): str(v or "").strip() for k, v in original.items() if k}
        if fila.get("apellido") in {"---", "-"} and fila.get("nombres") in {"---", "-", ""}:
            advertencias.append(f"Fila {numero_fila}: se omitió un casillero vacío marcado con guiones.")
            continue
        requeridos = (
            "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "claustro",
            "organo", "puesto", "apellido", "nombres", "tipo_candidatura", "orden",
        )
        vacios = [campo for campo in requeridos if not fila.get(campo)]
        if vacios:
            errores.append(f"Fila {numero_fila}: faltan valores en {', '.join(vacios)}.")
            continue
        tipo = _normalizar(fila["tipo_candidatura"])
        if tipo not in {Candidato.Tipo.TITULAR, Candidato.Tipo.SUPLENTE}:
            errores.append(f"Fila {numero_fila}: tipo_candidatura debe ser titular o suplente.")
            continue
        try:
            orden = int(fila["orden"])
            if orden < 1:
                raise ValueError
        except ValueError:
            errores.append(f"Fila {numero_fila}: orden debe ser un entero mayor que cero.")
            continue

        clave_config = (
            _normalizar(fila["claustro"]), _normalizar(fila["organo"]), _normalizar(fila["puesto"]),
            _normalizar(fila.get("departamento", "")),
        )
        config = mapa.get(clave_config)
        if config is None:
            errores.append(f"Fila {numero_fila}: el puesto no está habilitado para ese claustro y departamento.")
            continue
        limite = config.cantidad_titulares if tipo == Candidato.Tipo.TITULAR else config.cantidad_suplentes
        if orden > limite:
            errores.append(f"Fila {numero_fila}: el orden {orden} supera los {limite} puestos {tipo} configurados.")
            continue

        codigo, clave_codigo = fila["codigo_presentacion"], _normalizar(fila["codigo_presentacion"])
        metadatos = (
            fila["numero_lista"], fila["nombre_lista"], fila["apoderado_nombre"],
            fila.get("apoderado_email", ""), config.eleccion_claustro_id,
        )
        if clave_codigo in metadatos_presentaciones and metadatos_presentaciones[clave_codigo] != metadatos:
            errores.append(f"Fila {numero_fila}: los datos de la presentación {codigo} no son consistentes.")
            continue
        metadatos_presentaciones[clave_codigo] = metadatos
        clave_espacio = (clave_codigo, config.pk, tipo, orden)
        if clave_espacio in espacios:
            errores.append(f"Fila {numero_fila}: se repite el mismo puesto, tipo y orden en la presentación.")
            continue
        espacios.add(clave_espacio)

        identificador = fila.get("identificador_persona", "")
        if identificador:
            apariciones_identificador[_normalizar(identificador)].add(clave_codigo)
        filas_validas.append({
            "numero_fila": numero_fila, "codigo_presentacion": codigo, "numero_lista": fila["numero_lista"],
            "nombre_lista": fila["nombre_lista"], "apoderado_nombre": fila["apoderado_nombre"],
            "apoderado_email": fila.get("apoderado_email", ""), "puesto_eleccion_id": config.pk,
            "identificador_persona": identificador, "dni": fila.get("dni", ""), "apellido": fila["apellido"],
            "nombres": fila["nombres"], "tipo": tipo, "orden": orden,
        })

    for identificador, codigos in apariciones_identificador.items():
        if len(codigos) > 1:
            advertencias.append(f"El identificador {identificador} aparece en más de una presentación; requiere revisión.")
    estado = ImportacionCandidaturas.Estado.PREVISUALIZADA if not errores else ImportacionCandidaturas.Estado.RECHAZADA
    return ImportacionCandidaturas.objects.create(
        eleccion=eleccion, usuario=usuario, nombre_archivo=archivo.name[:255], estado=estado,
        filas=filas_validas, errores=errores, advertencias=advertencias,
        cantidad_total=cantidad_total, cantidad_valida=len(filas_validas),
    )


@transaction.atomic
def confirmar_importacion_candidaturas(importacion):
    importacion = ImportacionCandidaturas.objects.select_for_update().select_related("eleccion").get(pk=importacion.pk)
    if importacion.estado != ImportacionCandidaturas.Estado.PREVISUALIZADA or importacion.errores:
        raise ValidationError("La importación no está disponible para confirmar.")
    presentaciones, listas = {}, {}
    candidatos_creados = 0
    for fila in importacion.filas:
        config = PuestoEleccion.objects.select_related(
            "puesto", "eleccion_claustro", "eleccion_claustro_departamento",
        ).get(pk=fila["puesto_eleccion_id"], eleccion_claustro__eleccion=importacion.eleccion)
        codigo = fila["codigo_presentacion"]
        if codigo not in presentaciones:
            presentacion, _ = ParticipacionPartido.objects.update_or_create(
                eleccion=importacion.eleccion, codigo_presentacion=codigo,
                defaults={
                    "eleccion_claustro": config.eleccion_claustro, "numero_lista": fila["numero_lista"],
                    "nombre_lista": fila["nombre_lista"], "apoderado_nombre": fila["apoderado_nombre"],
                    "apoderado_email": fila["apoderado_email"], "activa": True,
                },
            )
            presentacion.full_clean()
            presentacion.save()
            presentaciones[codigo] = presentacion
        presentacion = presentaciones[codigo]
        clave_lista = (presentacion.pk, config.pk)
        if clave_lista not in listas:
            lista, _ = ListaCandidatos.objects.update_or_create(
                participacion=presentacion, puesto_eleccion=config,
                defaults={
                    "eleccion_claustro": config.eleccion_claustro,
                    "eleccion_claustro_departamento": config.eleccion_claustro_departamento,
                    "nombre": str(config.puesto), "activa": True,
                },
            )
            lista.full_clean()
            lista.save()
            listas[clave_lista] = lista
        candidato, creado = Candidato.objects.update_or_create(
            lista=listas[clave_lista], tipo=fila["tipo"], orden=fila["orden"],
            defaults={
                "nombre": f"{fila['apellido']}, {fila['nombres']}",
                "identificador_persona": fila["identificador_persona"], "dni": fila["dni"],
                "cargo": config.puesto.nombre, "activo": True,
            },
        )
        candidato.full_clean()
        candidato.save()
        candidatos_creados += int(creado)
    importacion.estado = ImportacionCandidaturas.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.save(update_fields=("estado", "confirmada_en"))
    return {"presentaciones": len(presentaciones), "listas": len(listas), "candidatos_creados": candidatos_creados, "filas": len(importacion.filas)}
