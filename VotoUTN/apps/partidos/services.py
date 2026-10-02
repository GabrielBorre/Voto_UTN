import csv
import io
import unicodedata
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.padron.models import RegistroPadron
from apps.partidos.models import Candidato, ImportacionCandidaturas, ListaCandidatos, ParticipacionPartido, PuestoEleccion


ENCABEZADOS_CANDIDATURAS = (
    "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email",
    "claustro", "organo", "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
ENCABEZADOS_OBLIGATORIOS = set(ENCABEZADOS_CANDIDATURAS) - {"apoderado_email", "tipo_documento", "documento"}
ENCABEZADOS_CANDIDATOS_LISTA = (
    "organo", "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
ENCABEZADOS_OBLIGATORIOS_CANDIDATOS = {
    "organo", "puesto", "tipo_candidatura", "orden",
}


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


def _leer_csv(archivo, encabezados_obligatorios=ENCABEZADOS_OBLIGATORIOS):
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
    faltantes = sorted(encabezados_obligatorios - encabezados)
    if not {"tipo_documento", "documento"}.issubset(encabezados) and "dni" not in encabezados:
        faltantes.extend(["tipo_documento", "documento"])
    if faltantes:
        raise ValidationError(f"Faltan columnas obligatorias: {', '.join(faltantes)}.")
    return lector


TIPOS_DOCUMENTO_CANDIDATO = (("DNI", "DNI"), ("CUIL", "CUIL"), ("LEGAJO", "Legajo"))


def buscar_elector_candidato(*, eleccion, tipo_documento, documento, puesto):
    """Una identidad del padrón activo, con el alcance del puesto; nunca infiere CUIL."""
    tipo_documento = str(tipo_documento or "").strip().upper()
    documento = str(documento or "").strip()
    if tipo_documento not in dict(TIPOS_DOCUMENTO_CANDIDATO) or not documento:
        raise ValidationError("Seleccione un tipo de documento e ingrese su número.")
    if tipo_documento == "LEGAJO":
        if len(documento) > 20:
            raise ValidationError("El legajo no puede superar 20 caracteres.")
        filtro = {"elector__legajo": documento}
    else:
        documento = documento.replace(".", "").replace("-", "").replace(" ", "")
        if not documento.isascii() or not documento.isdigit() or len(documento) > 12:
            raise ValidationError("El documento debe contener hasta 12 dígitos.")
        filtro = {"elector__dni": documento, "elector__tipo_documento__iexact": tipo_documento}
    registro = RegistroPadron.objects.select_related(
        "elector", "eleccion_claustro_departamento",
    ).filter(eleccion=eleccion, activo=True, **filtro).first()
    if registro is None:
        raise ValidationError("El documento no pertenece al padrón activo de esta elección.")
    alcance = registro.eleccion_claustro_departamento
    if alcance.eleccion_claustro_id != puesto.eleccion_claustro_id:
        raise ValidationError("El elector pertenece a otro claustro del padrón.")
    if puesto.eleccion_claustro_departamento_id and alcance.id != puesto.eleccion_claustro_departamento_id:
        raise ValidationError("El elector pertenece a otro departamento del padrón.")
    return registro.elector


def _identidad_fila(fila):
    # Compatibilidad con archivos anteriores: dni siempre significa tipo DNI.
    if "documento" in fila:
        return {"tipo_documento": fila.get("tipo_documento", ""), "documento": fila["documento"]}
    return {"tipo_documento": "DNI", "documento": fila.get("dni", "")}


def previsualizar_candidatos_lista(*, participacion, archivo, usuario):
    """Valida candidatos para puestos ya vinculados a una lista existente."""
    errores, advertencias, filas_validas = [], [], []
    cantidad_total = 0
    filas_leidas = 0
    try:
        lector = _leer_csv(archivo, ENCABEZADOS_OBLIGATORIOS_CANDIDATOS)
    except ValidationError as error:
        return ImportacionCandidaturas.objects.create(
            eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
            estado=ImportacionCandidaturas.Estado.RECHAZADA, errores=error.messages,
        )

    posiciones = participacion.listas.filter(
        activa=True, puesto_eleccion__activo=True, puesto_eleccion__puesto__activo=True,
        puesto_eleccion__puesto__organo__activo=True,
    ).select_related("puesto_eleccion__puesto__organo", "eleccion_claustro_departamento__departamento")
    mapa = {}
    for lista in posiciones:
        config = lista.puesto_eleccion
        clave = (
            _normalizar(config.puesto.organo.nombre), _normalizar(config.puesto.nombre),
            _normalizar(lista.eleccion_claustro_departamento.departamento.nombre)
            if lista.eleccion_claustro_departamento_id else "",
        )
        mapa[clave] = lista

    espacios = set()
    electores_advertidos = set()
    for numero_fila, original in enumerate(lector, start=2):
        filas_leidas += 1
        if filas_leidas > 5000:
            errores.append("El archivo supera el máximo de 5000 filas.")
            break
        fila = {_normalizar(k).replace(" ", "_"): str(v or "").strip() for k, v in original.items() if k}
        if not any(fila.get(campo) for campo in ("documento", "dni", "apellido", "nombres", "identificador_persona")):
            continue
        cantidad_total += 1
        vacios = [campo for campo in ENCABEZADOS_OBLIGATORIOS_CANDIDATOS if not fila.get(campo)]
        if vacios:
            errores.append(f"Fila {numero_fila}: faltan valores en {', '.join(sorted(vacios))}.")
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
        clave_puesto = (
            _normalizar(fila["organo"]), _normalizar(fila["puesto"]),
            _normalizar(fila.get("departamento", "")),
        )
        lista = mapa.get(clave_puesto)
        if lista is None:
            errores.append(f"Fila {numero_fila}: el puesto no está asociado a esta lista.")
            continue
        clave_espacio = (lista.pk, tipo, orden)
        if clave_espacio in espacios:
            errores.append(f"Fila {numero_fila}: se repite el puesto, tipo y orden en el archivo.")
            continue
        espacios.add(clave_espacio)
        try:
            elector = buscar_elector_candidato(
                eleccion=participacion.eleccion, **_identidad_fila(fila), puesto=lista.puesto_eleccion,
            )
        except ValidationError as error:
            errores.append(f"Fila {numero_fila}: {'; '.join(error.messages)}")
            continue
        candidato = Candidato(
            lista=lista, elector=elector, tipo=tipo, orden=orden,
            cargo=lista.puesto_eleccion.puesto.nombre,
        )
        try:
            candidato.full_clean()
        except ValidationError as error:
            errores.append(f"Fila {numero_fila}: {'; '.join(error.messages)}")
            continue
        if elector.pk not in electores_advertidos and Candidato.objects.filter(
            elector=elector,
        ).exclude(lista__participacion=participacion).exists():
            advertencias.append(
                f"El DNI {elector.dni} aparece en otra presentación; requiere revisión."
            )
            electores_advertidos.add(elector.pk)
        filas_validas.append({
            "numero_fila": numero_fila, "participacion_id": participacion.pk,
            "lista_id": lista.pk, "puesto_eleccion_id": lista.puesto_eleccion_id,
            "nombre_puesto": str(lista.puesto_eleccion),
            "elector_id": elector.pk, "dni": elector.dni, "nombre": elector.nombre_completo,
            **_identidad_fila(fila),
            "tipo": tipo, "orden": orden,
        })

    if not filas_validas and not errores:
        errores.append("El archivo no contiene candidatos para cargar.")
    estado = ImportacionCandidaturas.Estado.RECHAZADA if errores else ImportacionCandidaturas.Estado.PREVISUALIZADA
    return ImportacionCandidaturas.objects.create(
        eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
        estado=estado, filas=filas_validas, errores=errores, advertencias=advertencias,
        cantidad_total=cantidad_total, cantidad_valida=len(filas_validas),
    )


@transaction.atomic
def confirmar_candidatos_lista(importacion, participacion):
    importacion = ImportacionCandidaturas.objects.select_for_update().get(
        pk=importacion.pk, eleccion=participacion.eleccion,
    )
    if importacion.estado != ImportacionCandidaturas.Estado.PREVISUALIZADA or importacion.errores:
        raise ValidationError("La importación no está disponible para confirmar.")
    if not importacion.filas or any(
        fila.get("participacion_id") != participacion.pk for fila in importacion.filas
    ):
        raise ValidationError("La importación no corresponde a esta lista.")

    for fila in importacion.filas:
        lista = ListaCandidatos.objects.select_related("puesto_eleccion__puesto").get(
            pk=fila["lista_id"], participacion=participacion, activa=True,
            puesto_eleccion_id=fila["puesto_eleccion_id"], puesto_eleccion__activo=True,
        )
        elector = buscar_elector_candidato(
            eleccion=participacion.eleccion, **_identidad_fila(fila), puesto=lista.puesto_eleccion,
        )
        if fila.get("elector_id") and elector.pk != fila["elector_id"]:
            raise ValidationError("El elector de la previsualización cambió.")
        candidato = Candidato(
            lista=lista, elector=elector,
            tipo=fila["tipo"], orden=fila["orden"], cargo=lista.puesto_eleccion.puesto.nombre,
        )
        candidato.full_clean()
        candidato.save()
    importacion.estado = ImportacionCandidaturas.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.save(update_fields=("estado", "confirmada_en"))
    return len(importacion.filas)


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
    apariciones_elector = defaultdict(set)
    for numero_fila, original in enumerate(lector, start=2):
        cantidad_total += 1
        if cantidad_total > 5000:
            errores.append("El archivo supera el máximo de 5000 filas.")
            break
        fila = {_normalizar(k).replace(" ", "_"): str(v or "").strip() for k, v in original.items() if k}
        if _identidad_fila(fila)["documento"] in {"---", "-"}:
            advertencias.append(f"Fila {numero_fila}: se omitió un casillero vacío marcado con guiones.")
            continue
        requeridos = (
            "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "claustro",
            "organo", "puesto", "tipo_candidatura", "orden",
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
        try:
            elector = buscar_elector_candidato(eleccion=eleccion, **_identidad_fila(fila), puesto=config)
        except ValidationError as error:
            errores.append(f"Fila {numero_fila}: {'; '.join(error.messages)}")
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

        apariciones_elector[elector.pk].add(clave_codigo)
        filas_validas.append({
            "numero_fila": numero_fila, "codigo_presentacion": codigo, "numero_lista": fila["numero_lista"],
            "nombre_lista": fila["nombre_lista"], "apoderado_nombre": fila["apoderado_nombre"],
            "apoderado_email": fila.get("apoderado_email", ""), "puesto_eleccion_id": config.pk,
            "elector_id": elector.pk, "dni": elector.dni, "nombre": elector.nombre_completo,
            **_identidad_fila(fila),
            "tipo": tipo, "orden": orden,
        })

    for elector_id, codigos in apariciones_elector.items():
        if len(codigos) > 1:
            dni = next(fila["dni"] for fila in filas_validas if fila["elector_id"] == elector_id)
            advertencias.append(f"El DNI {dni} aparece en más de una presentación; requiere revisión.")
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
        elector = buscar_elector_candidato(eleccion=importacion.eleccion, **_identidad_fila(fila), puesto=config)
        if fila.get("elector_id") and elector.pk != fila["elector_id"]:
            raise ValidationError("El elector de la previsualización cambió.")
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
        candidato = Candidato.objects.filter(
            lista=listas[clave_lista], tipo=fila["tipo"], orden=fila["orden"],
        ).first()
        creado = candidato is None
        if creado:
            candidato = Candidato(lista=listas[clave_lista], tipo=fila["tipo"], orden=fila["orden"])
        candidato.elector = elector
        candidato.identificador_persona = ""
        candidato.cargo = config.puesto.nombre
        candidato.activo = True
        candidato.full_clean()
        candidato.save()
        candidatos_creados += int(creado)
    importacion.estado = ImportacionCandidaturas.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.save(update_fields=("estado", "confirmada_en"))
    return {"presentaciones": len(presentaciones), "listas": len(listas), "candidatos_creados": candidatos_creados, "filas": len(importacion.filas)}
