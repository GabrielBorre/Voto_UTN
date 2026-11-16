import csv
import io
import re
import unicodedata
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import EleccionClaustro
from apps.padron.models import RegistroPadron
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ImportacionCandidaturas,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    PuestoEleccion,
)
from apps.reportes.services import valor_csv


ENCABEZADOS_CANDIDATURAS = (
    "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email",
    "claustro", "organo", "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
ENCABEZADOS_OBLIGATORIOS = set(ENCABEZADOS_CANDIDATURAS) - {"apoderado_email", "tipo_documento", "documento"}
ENCABEZADOS_CANDIDATOS_LISTA = (
    "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
ENCABEZADOS_CANDIDATOS_MULTIPUESTO = (
    "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
ENCABEZADOS_OBLIGATORIOS_CANDIDATOS = {"tipo_candidatura", "orden"}


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "").strip())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).casefold().split())


CLAUSTROS_CON_PUESTOS_DEPARTAMENTALES_PREDETERMINADOS = {
    "estudiantes",
    "docentes",
    "graduados",
}
COMPOSICION_PUESTOS_DEPARTAMENTALES_POR_CLAUSTRO = {
    "docentes": 5,
    "estudiantes": 3,
    "graduados": 2,
}


@transaction.atomic
def habilitar_puestos_departamentales_predeterminados(eleccion_claustro):
    """Crea puestos departamentales faltantes para un claustro y sus departamentos."""
    if _normalizar(eleccion_claustro.claustro.nombre) not in (
        CLAUSTROS_CON_PUESTOS_DEPARTAMENTALES_PREDETERMINADOS
    ):
        return []

    organo, _ = OrganoElectivo.objects.get_or_create(
        nombre="Consejo Departamental",
        defaults={"descripcion": "Órgano de gobierno de cada departamento académico."},
    )
    cargo, _ = CargoElectivo.objects.get_or_create(
        organo=organo,
        nombre="Consejero/a departamental",
        defaults={
            "permite_filtrar_claustros": True,
            "permite_filtrar_departamentos": True,
            "descripcion": "Representación departamental con composición definida por claustro.",
            "activo": True,
        },
    )
    cargo.claustros_habilitados.add(eleccion_claustro.claustro)
    cantidad_representantes = COMPOSICION_PUESTOS_DEPARTAMENTALES_POR_CLAUSTRO[
        _normalizar(eleccion_claustro.claustro.nombre)
    ]

    configuraciones = eleccion_claustro.departamentos.filter(
        departamento__isnull=False,
    ).select_related("departamento")
    puestos_creados = []
    for configuracion in configuraciones:
        if configuracion.departamento.codigo.casefold() == "z" or (
            _normalizar(configuracion.departamento.nombre) == "ciencias basicas"
        ):
            continue
        puesto, creado = PuestoEleccion.objects.get_or_create(
            puesto=cargo,
            eleccion_claustro=eleccion_claustro,
            eleccion_claustro_departamento=configuracion,
            defaults={
                "cantidad_titulares": cantidad_representantes,
                "cantidad_suplentes": cantidad_representantes,
                "activo": True,
            },
        )
        if creado:
            puestos_creados.append(puesto)
    return puestos_creados


@transaction.atomic
def guardar_con_validacion(formulario, **relaciones):
    instancia = formulario.save(commit=False)
    for nombre, valor in relaciones.items():
        setattr(instancia, nombre, valor)
    instancia.full_clean()
    instancia.save()
    return instancia


@transaction.atomic
def crear_presentacion_con_puestos(formulario, **relaciones):
    participacion = formulario.save(commit=False)
    for nombre, valor in relaciones.items():
        setattr(participacion, nombre, valor)
    participacion.full_clean()
    participacion.save()

    configuraciones_creadas = []
    cargo_nuevo = formulario.cleaned_data["puesto_nuevo"]
    if cargo_nuevo:
        departamento = formulario.cleaned_data["departamento_puesto_nuevo"]
        claustros = EleccionClaustro.objects.filter(pk=participacion.eleccion_claustro_id)
        if not cargo_nuevo.permite_filtrar_claustros and not departamento:
            claustros = EleccionClaustro.objects.filter(
                eleccion=participacion.eleccion,
                claustro__in=cargo_nuevo.claustros_habilitados.all(),
            )
        for claustro in claustros:
            configuracion = PuestoEleccion(
                puesto=cargo_nuevo,
                eleccion_claustro=claustro,
                eleccion_claustro_departamento=departamento,
                cantidad_titulares=formulario.cleaned_data["cantidad_titulares_nueva"],
                cantidad_suplentes=formulario.cleaned_data["cantidad_suplentes_nueva"] or 0,
            )
            configuracion.full_clean()
            configuracion.save()
            configuraciones_creadas.append(configuracion)

    listas = []
    puestos = list(formulario.cleaned_data["puestos_eleccion"])
    puestos.extend(
        configuracion
        for configuracion in configuraciones_creadas
        if configuracion.eleccion_claustro_id == participacion.eleccion_claustro_id
    )
    for puesto_eleccion in puestos:
        lista = ListaCandidatos(
            participacion=participacion,
            eleccion_claustro=puesto_eleccion.eleccion_claustro,
            eleccion_claustro_departamento=puesto_eleccion.eleccion_claustro_departamento,
            nombre=str(puesto_eleccion.puesto),
            puesto_eleccion=puesto_eleccion,
        )
        lista.full_clean()
        lista.save()
        listas.append(lista)
    return participacion, listas, configuraciones_creadas


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
    if dialecto.quotechar == "'" and re.search(r"(?:^|[;,\r\n])'[=+\-@]", contenido):
        dialecto.quotechar = '"'
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
        filtro = {"legajo": documento}
    else:
        documento = documento.replace(".", "").replace("-", "").replace(" ", "")
        if not documento.isascii() or not documento.isdigit() or len(documento) > 12:
            raise ValidationError("El documento debe contener hasta 12 dígitos.")
        filtro = {"elector__dni": documento, "elector__tipo_documento__iexact": tipo_documento}
    registros = RegistroPadron.objects.select_related(
        "elector", "eleccion_claustro_departamento",
    ).filter(eleccion=eleccion, activo=True, **filtro)
    if not registros.exists():
        raise ValidationError("El documento no pertenece al padrón activo de esta elección.")
    registros = registros.filter(
        eleccion_claustro_departamento__eleccion_claustro_id=puesto.eleccion_claustro_id,
    )
    if not registros.exists():
        raise ValidationError("El elector pertenece a otro claustro del padrón.")
    if puesto.eleccion_claustro_departamento_id:
        registros = registros.filter(eleccion_claustro_departamento_id=puesto.eleccion_claustro_departamento_id)
    registro = registros.first()
    if registro is None:
        raise ValidationError("El elector pertenece a otro departamento del padrón.")
    return registro.elector


def _identidad_fila(fila):
    # Compatibilidad con archivos anteriores: dni siempre significa tipo DNI.
    if "documento" in fila:
        return {"tipo_documento": fila.get("tipo_documento", ""), "documento": fila["documento"]}
    return {"tipo_documento": "DNI", "documento": fila.get("dni", "")}


def previsualizar_candidatos_multipuesto(*, participacion, archivo, usuario):
    errores, advertencias, filas_validas = [], [], []
    cantidad_total = 0
    if not participacion.activa or not participacion.eleccion_claustro_id:
        return ImportacionCandidaturas.objects.create(
            eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
            estado=ImportacionCandidaturas.Estado.RECHAZADA,
            errores=["La lista debe estar activa y tener un claustro asignado."],
        )
    try:
        lector = _leer_csv(
            archivo, ENCABEZADOS_OBLIGATORIOS_CANDIDATOS | {"puesto", "departamento"},
        )
    except ValidationError as error:
        return ImportacionCandidaturas.objects.create(
            eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
            estado=ImportacionCandidaturas.Estado.RECHAZADA, errores=error.messages,
        )

    configuraciones = PuestoEleccion.objects.filter(
        eleccion_claustro_id=participacion.eleccion_claustro_id,
        puesto__claustros_habilitados=participacion.eleccion_claustro.claustro_id,
        activo=True, puesto__activo=True, puesto__organo__activo=True,
    ).select_related("puesto__organo", "eleccion_claustro_departamento__departamento")
    mapa = defaultdict(list)
    for config in configuraciones:
        if config.eleccion_claustro_departamento_id and not config.eleccion_claustro_departamento.departamento_id:
            continue
        departamento = (
            config.eleccion_claustro_departamento.departamento.nombre
            if config.eleccion_claustro_departamento_id else ""
        )
        mapa[(_normalizar(config.puesto.nombre), _normalizar(departamento))].append(config)
    asociaciones = {
        lista.puesto_eleccion_id: lista
        for lista in participacion.listas.filter(puesto_eleccion__isnull=False).select_related(
            "puesto_eleccion__puesto", "eleccion_claustro_departamento",
        )
    }
    espacios, personas = set(), set()
    for numero_fila, original in enumerate(lector, start=2):
        if numero_fila > 5001:
            errores.append("El archivo supera el máximo de 5000 filas.")
            break
        fila = {_normalizar(k).replace(" ", "_"): str(v or "").strip() for k, v in original.items() if k}
        if not any(fila.values()):
            continue
        cantidad_total += 1
        vacios = [campo for campo in ("puesto", "tipo_candidatura", "orden") if not fila.get(campo)]
        if not _identidad_fila(fila)["documento"]:
            vacios.append("documento")
        if "documento" in fila and not fila.get("tipo_documento"):
            vacios.append("tipo_documento")
        if vacios:
            errores.append(f"Fila {numero_fila}: faltan valores en {', '.join(vacios)}.")
            continue
        configs = mapa.get((_normalizar(fila["puesto"]), _normalizar(fila["departamento"])), [])
        if len(configs) != 1:
            errores.append(
                f"Fila {numero_fila}: el puesto y departamento no identifican un único puesto habilitado."
            )
            continue
        config = configs[0]
        lista = asociaciones.get(config.pk)
        if lista and not lista.activa:
            errores.append(f"Fila {numero_fila}: el puesto está asociado a la lista pero está inactivo.")
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
        limite = config.cantidad_titulares if tipo == Candidato.Tipo.TITULAR else config.cantidad_suplentes
        if orden > limite:
            errores.append(f"Fila {numero_fila}: el orden supera los {limite} puestos {tipo} configurados.")
            continue
        espacio = (config.pk, tipo, orden)
        if espacio in espacios or (lista and lista.candidatos.filter(tipo=tipo, orden=orden).exists()):
            errores.append(f"Fila {numero_fila}: el puesto, tipo y orden ya están ocupados o repetidos.")
            continue
        try:
            elector = buscar_elector_candidato(
                eleccion=participacion.eleccion, puesto=config, **_identidad_fila(fila),
            )
            if (config.pk, elector.pk) in personas or (
                lista and lista.candidatos.filter(dni=elector.dni).exists()
            ):
                raise ValidationError("El elector ya figura en este puesto.")
            if lista:
                Candidato(
                    lista=lista, elector=elector, tipo=tipo, orden=orden, cargo=config.puesto.nombre,
                ).full_clean()
            elif AsignacionAutoridad.objects.filter(
                registro_padron__elector=elector, registro_padron__eleccion=participacion.eleccion,
                estado="asignada",
            ).exists():
                raise ValidationError(
                    "El elector es autoridad de mesa. Quitá su designación antes de incorporarlo como candidato electoral."
                )
        except ValidationError as error:
            errores.append(f"Fila {numero_fila}: {'; '.join(error.messages)}")
            continue
        espacios.add(espacio)
        personas.add((config.pk, elector.pk))
        if Candidato.objects.filter(elector=elector).exclude(lista__participacion=participacion).exists():
            aviso = f"El DNI {elector.dni} aparece en otra presentación; requiere revisión."
            if aviso not in advertencias:
                advertencias.append(aviso)
        filas_validas.append({
            "modalidad": "multipuesto", "numero_fila": numero_fila,
            "participacion_id": participacion.pk, "puesto_eleccion_id": config.pk,
            "cargo_electivo_id": config.puesto_id,
            "alcance_id": config.eleccion_claustro_departamento_id,
            "nombre_puesto": str(config), "elector_id": elector.pk,
            "nombre": elector.nombre_completo, **_identidad_fila(fila),
            "tipo": tipo, "orden": orden,
        })

    if not filas_validas and not errores:
        errores.append("El archivo no contiene candidatos para cargar.")
    return ImportacionCandidaturas.objects.create(
        eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
        estado=ImportacionCandidaturas.Estado.RECHAZADA if errores else ImportacionCandidaturas.Estado.PREVISUALIZADA,
        filas=filas_validas, errores=errores, advertencias=advertencias,
        cantidad_total=cantidad_total, cantidad_valida=len(filas_validas),
    )


@transaction.atomic
def confirmar_candidatos_multipuesto(importacion, participacion):
    participacion = ParticipacionPartido.objects.select_for_update().get(pk=participacion.pk)
    importacion = ImportacionCandidaturas.objects.select_for_update().get(
        pk=importacion.pk, eleccion=participacion.eleccion,
    )
    if importacion.estado != ImportacionCandidaturas.Estado.PREVISUALIZADA or importacion.errores:
        raise ValidationError("La importación no está disponible para confirmar.")
    if not participacion.activa or not importacion.filas or any(
        fila.get("modalidad") != "multipuesto" or fila.get("participacion_id") != participacion.pk
        for fila in importacion.filas
    ):
        raise ValidationError("La importación no corresponde a esta lista activa.")
    listas = {}
    for fila in importacion.filas:
        config = PuestoEleccion.objects.select_for_update(of=("self",)).select_related(
            "puesto__organo", "eleccion_claustro", "eleccion_claustro_departamento",
        ).filter(
            pk=fila["puesto_eleccion_id"], eleccion_claustro_id=participacion.eleccion_claustro_id,
            puesto__claustros_habilitados=participacion.eleccion_claustro.claustro_id,
            activo=True, puesto__activo=True, puesto__organo__activo=True,
        ).first()
        if config is None:
            raise ValidationError("Un puesto de la previsualización ya no está habilitado para la lista.")
        if (
            config.puesto_id != fila["cargo_electivo_id"]
            or config.eleccion_claustro_departamento_id != fila["alcance_id"]
        ):
            raise ValidationError("Cambió el alcance de un puesto desde la previsualización.")
        if config.pk not in listas:
            lista = ListaCandidatos.objects.select_for_update().filter(
                participacion=participacion, puesto_eleccion=config,
            ).first()
            if lista and not lista.activa:
                raise ValidationError("Un puesto de la lista está inactivo.")
            if lista is None:
                lista = ListaCandidatos(
                    participacion=participacion, puesto_eleccion=config,
                    eleccion_claustro=config.eleccion_claustro,
                    eleccion_claustro_departamento=config.eleccion_claustro_departamento,
                    nombre=str(config.puesto),
                )
                lista.full_clean()
                lista.save()
            listas[config.pk] = lista
        elector = buscar_elector_candidato(
            eleccion=participacion.eleccion, puesto=config, **_identidad_fila(fila),
        )
        if elector.pk != fila["elector_id"]:
            raise ValidationError("El elector de la previsualización cambió.")
        candidato = Candidato(
            lista=listas[config.pk], elector=elector, tipo=fila["tipo"],
            orden=fila["orden"], cargo=config.puesto.nombre,
        )
        candidato.full_clean()
        candidato.save()
    importacion.estado = ImportacionCandidaturas.Estado.CONFIRMADA
    importacion.confirmada_en = timezone.now()
    importacion.save(update_fields=("estado", "confirmada_en"))
    return len(importacion.filas)


def previsualizar_candidatos_lista(*, lista, archivo, usuario):
    """Valida candidatos para un puesto ya vinculado a una lista existente."""
    errores, advertencias, filas_validas = [], [], []
    cantidad_total = 0
    filas_leidas = 0
    participacion = lista.participacion
    try:
        lector = _leer_csv(archivo, ENCABEZADOS_OBLIGATORIOS_CANDIDATOS)
    except ValidationError as error:
        return ImportacionCandidaturas.objects.create(
            eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
            estado=ImportacionCandidaturas.Estado.RECHAZADA, errores=error.messages,
        )

    if not lista.activa or not lista.puesto_eleccion_id or not lista.puesto_eleccion.activo:
        errores.append("El puesto seleccionado no está activo para esta lista.")
        return ImportacionCandidaturas.objects.create(
            eleccion=participacion.eleccion, usuario=usuario, nombre_archivo=archivo.name[:255],
            estado=ImportacionCandidaturas.Estado.RECHAZADA, errores=errores,
        )

    espacios = set()
    electores_advertidos = set()
    for numero_fila, original in enumerate(lector, start=2):
        filas_leidas += 1
        if filas_leidas > 5000:
            errores.append("El archivo supera el máximo de 5000 filas.")
            break
        fila = {_normalizar(k).replace(" ", "_"): str(v or "").strip() for k, v in original.items() if k}
        if not any(fila.get(campo) for campo in ("documento", "dni")):
            continue
        cantidad_total += 1
        vacios = [
            campo for campo in ("tipo_candidatura", "orden")
            if not fila.get(campo)
        ]
        if not fila.get("documento") and not fila.get("dni"):
            vacios.append("documento")
        if "documento" in fila and not fila.get("tipo_documento"):
            vacios.append("tipo_documento")
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
        config = lista.puesto_eleccion
        departamento = (
            lista.eleccion_claustro_departamento.departamento.nombre
            if lista.eleccion_claustro_departamento_id
            else ""
        )
        metadatos_puesto = {
            "organo": config.puesto.organo.nombre,
            "puesto": config.puesto.nombre,
            "departamento": departamento,
        }
        valores_puesto_incompatibles = [
            campo for campo, valor in metadatos_puesto.items()
            if fila.get(campo) and _normalizar(fila[campo]) not in {
                _normalizar(valor), _normalizar(valor_csv(valor)),
            }
        ]
        if valores_puesto_incompatibles:
            errores.append(f"Fila {numero_fila}: los datos de puesto no coinciden con el puesto seleccionado.")
            continue
        clave_espacio = (tipo, orden)
        if clave_espacio in espacios:
            errores.append(f"Fila {numero_fila}: se repite el tipo y orden en el puesto seleccionado.")
            continue
        espacios.add(clave_espacio)
        try:
            elector = buscar_elector_candidato(
                eleccion=participacion.eleccion, **_identidad_fila(fila), puesto=config,
            )
        except ValidationError as error:
            errores.append(f"Fila {numero_fila}: {'; '.join(error.messages)}")
            continue
        candidato = Candidato(
            lista=lista, elector=elector, tipo=tipo, orden=orden,
            cargo=config.puesto.nombre,
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
            "nombre_puesto": str(config),
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
def confirmar_candidatos_lista(importacion, lista_seleccionada):
    participacion = lista_seleccionada.participacion
    importacion = ImportacionCandidaturas.objects.select_for_update().get(
        pk=importacion.pk, eleccion=participacion.eleccion,
    )
    if importacion.estado != ImportacionCandidaturas.Estado.PREVISUALIZADA or importacion.errores:
        raise ValidationError("La importación no está disponible para confirmar.")
    if not importacion.filas or any(
        fila.get("participacion_id") != participacion.pk
        or fila.get("lista_id") != lista_seleccionada.pk
        for fila in importacion.filas
    ):
        raise ValidationError("La importación no corresponde al puesto seleccionado.")

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
