import csv
import io
from collections import Counter
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustro, EleccionClaustroDepartamentoSede
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import AsignacionSedePadron, RegistroPadron


PLANTILLA_NOMINA_HEADERS = ("Tipo documento", "Documento", "Legajo")

def leer_filas_autoridades(contenido: bytes, nombre_archivo: str = "") -> list[dict[str, str]]:
    nombre_archivo = (nombre_archivo or "").lower()
    if nombre_archivo.endswith(".xls"):
        raise ValueError("El formato .xls no es compatible. Guardá la planilla como .xlsx o CSV.")
    if nombre_archivo.endswith(".xlsx"):
        try:
            libro = load_workbook(filename=io.BytesIO(contenido), read_only=True, data_only=True)
        except (BadZipFile, InvalidFileException, OSError, ParseError, ValueError) as exc:
            raise ValueError("No se pudo leer el archivo Excel. Verificá que sea un .xlsx válido.") from exc
        try:
            filas = list(libro.active.iter_rows(values_only=True))
            if not filas:
                return []
            encabezados = [str(valor).strip() if valor is not None else "" for valor in filas[0]]
            registros = []
            for numero, fila in enumerate(filas[1:], start=2):
                if not any(valor is not None and str(valor).strip() for valor in fila):
                    continue
                if any(
                    valor is not None
                    and str(valor).strip()
                    and (indice >= len(encabezados) or not encabezados[indice])
                    for indice, valor in enumerate(fila)
                ):
                    raise ValueError(f"La fila {numero} contiene datos sin una cabecera.")
                registros.append({
                    nombre: "" if indice >= len(fila) or fila[indice] is None else str(fila[indice]).strip()
                    for indice, nombre in enumerate(encabezados)
                })
            return registros
        finally:
            libro.close()

    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("El archivo debe estar codificado en UTF-8.") from exc

    try:
        dialecto = csv.Sniffer().sniff(texto[:8192], delimiters=",;")
    except csv.Error:
        dialecto = csv.excel
    lector = csv.DictReader(io.StringIO(texto, newline=""), dialect=dialecto)
    filas = []
    for numero, fila in enumerate(lector, start=2):
        if not fila:
            continue
        if None in fila:
            raise ValueError(f"La fila {numero} contiene más columnas que las cabeceras.")
        filas.append({(clave or "").strip(): (valor or "").strip() for clave, valor in fila.items()})
    return filas


@transaction.atomic
def asignar_autoridad(registro_padron, mesa, turno, usuario):
    Eleccion.objects.select_for_update().get(pk=registro_padron.eleccion_id)
    eleccion_claustro = mesa.eleccion_claustro_departamento.eleccion_claustro
    if not eleccion_claustro.turnos_autoridad.filter(turno=turno).exists():
        raise ValidationError("El turno de trabajo no está habilitado para este claustro.")
    configuracion_turno = eleccion_claustro.turnos_autoridad.get(turno=turno)
    if AsignacionAutoridad.objects.filter(mesa=mesa, turno=turno, tipo=AsignacionAutoridad.Tipo.TITULAR).exclude(estado=AsignacionAutoridad.Estado.RECHAZADA).count() >= configuracion_turno.titulares_por_mesa:
        raise ValidationError("La mesa ya alcanzó el máximo de autoridades configurado para este turno.")
    if not registro_padron.activo:
        raise ValidationError("Solo pueden asignarse electores activos del padrón.")
    if registro_padron.eleccion_claustro_departamento_id != mesa.eleccion_claustro_departamento_id:
        raise ValidationError("La autoridad y la mesa deben pertenecer al mismo departamento.")
    if registro_padron.sede_id and not registro_padron.turno_cursada_id:
        raise ValidationError("Completá el horario de asistencia a la sede antes de asignar esta autoridad.")
    if registro_padron.turno_cursada_id and registro_padron.turno_cursada.se_superpone_con(turno):
        raise ValidationError("El turno de trabajo se superpone con el horario de asistencia a la sede.")
    sede_electoral = _sede_electoral_actual(registro_padron)
    if sede_electoral is not None and sede_electoral != mesa.sede_id:
        raise ValidationError("La autoridad debe asignarse en la sede electoral que ya tiene asignada.")
    candidatura, _ = CandidaturaAutoridad.objects.get_or_create(registro_padron=registro_padron, defaults={"cargada_por": usuario})
    mesa_original = getattr(registro_padron, "asignacion_mesa", None)
    asignacion, creada = AsignacionAutoridad.objects.get_or_create(
        registro_padron=registro_padron,
        defaults={"mesa": mesa, "mesa_votacion_original_id": mesa_original.mesa_id if mesa_original else None,
                  "turno": turno, "candidatura": candidatura, "asignada_por": usuario},
    )
    if not creada and asignacion.mesa_id != mesa.id:
        raise ValidationError("El elector ya fue asignado como autoridad de otra mesa.")
    if not creada and asignacion.turno_id != turno.id:
        raise ValidationError("El elector ya fue asignado como autoridad en otro turno.")
    asignacion.full_clean()
    if creada:
        from apps.usuarios.models import AsignacionRol, PerfilUsuario

        perfil = PerfilUsuario.objects.filter(elector=registro_padron.elector, activo=True).select_related("usuario").first()
        if perfil:
            AsignacionRol.objects.get_or_create(
                usuario=perfil.usuario,
                rol=AsignacionRol.Rol.AUTORIDAD_MESA,
                eleccion=registro_padron.eleccion,
                sede=mesa.sede,
                mesa=mesa,
            )
    return asignacion, creada


def redistribuir_autoridades(eleccion_claustro, usuario, *, preservar_asignaciones=True):
    from apps.autoridades.distribucion import distribuir
    return distribuir(eleccion_claustro, usuario, preservar_asignaciones=preservar_asignaciones)


def _sede_electoral_actual(registro):
    asignacion_sede = getattr(registro, "asignacion_sede_padron", None)
    if asignacion_sede:
        return asignacion_sede.sede_id
    asignacion_mesa = getattr(registro, "asignacion_mesa", None)
    return asignacion_mesa.mesa.sede_id if asignacion_mesa else None


def _crear_asignacion(registro, mesa, turno, usuario, tipo, orden=None):
    candidatura = getattr(registro, "candidatura_autoridad", None)
    asignacion_mesa = getattr(registro, "asignacion_mesa", None)
    return AsignacionAutoridad(
        registro_padron=registro,
        candidatura=candidatura,
        mesa=mesa,
        mesa_votacion_original_id=asignacion_mesa.mesa_id if asignacion_mesa else None,
        turno=turno,
        tipo=tipo,
        orden_suplencia=orden,
        asignada_por=usuario or candidatura.cargada_por,
    )


def _sincronizar_rol_autoridad(asignacion):
    from apps.usuarios.models import AsignacionRol, PerfilUsuario

    perfil = PerfilUsuario.objects.filter(elector=asignacion.registro_padron.elector, activo=True).select_related("usuario").first()
    if perfil:
        AsignacionRol.objects.get_or_create(
            usuario=perfil.usuario,
            rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=asignacion.registro_padron.eleccion,
            sede=asignacion.mesa.sede,
            mesa=asignacion.mesa,
        )


def proponer_cambios_sede(eleccion_claustro, sin_cubrir):
    """Devuelve movimientos posibles sin aplicarlos, para confirmación expresa."""
    from apps.autoridades.distribucion import configuracion_actual, es_candidato_electoral
    opciones = configuracion_actual(eleccion_claustro)
    if opciones.modo != "nomina" or not opciones.permitir_cambio_sede:
        return []
    propuestas, usados = [], set()
    propuestos_por_plaza = Counter()
    deficits = Counter(mesa.sede.nombre if mesa.sede_id else "" for mesa, _turno in sin_cubrir)
    ordenados = sorted(
        sin_cubrir,
        key=lambda par: (
            -deficits[par[0].sede.nombre if par[0].sede_id else ""],
            par[0].sede.nombre.casefold() if par[0].sede_id else "",
            par[0].numero,
            par[1].hora_inicio,
        ),
    )
    for mesa, turno in ordenados:
        if mesa.eleccion_claustro_departamento.eleccion_claustro_id != eleccion_claustro.id:
            continue
        config = eleccion_claustro.turnos_autoridad.filter(turno=turno).first()
        ocupados = AsignacionAutoridad.objects.filter(mesa=mesa, turno=turno, tipo="titular", estado="asignada").count()
        if not config or ocupados + propuestos_por_plaza[(mesa.pk, turno.pk)] >= config.titulares_por_mesa:
            continue
        candidatos = CandidaturaAutoridad.objects.filter(
            registro_padron__activo=True,
            registro_padron__eleccion_claustro_departamento=mesa.eleccion_claustro_departamento,
            registro_padron__asignacion_sede_padron__estado=AsignacionSedePadron.Estado.ASIGNADA,
            registro_padron__asignacion_mesa__isnull=False,
            excluida=False,
        ).exclude(
            Q(registro_padron__asignacion_autoridad__tipo="titular", registro_padron__asignacion_autoridad__estado="asignada")
            | Q(registro_padron__asignacion_autoridad__estado="rechazada"),
        ).exclude(
            registro_padron__asignacion_sede_padron__sede=mesa.sede,
        ).select_related(
            "registro_padron__elector", "registro_padron__sede", "registro_padron__turno_cursada",
            "registro_padron__asignacion_sede_padron__sede", "registro_padron__asignacion_mesa__mesa",
        ).order_by("registro_padron__elector__apellido", "registro_padron__elector__nombre")
        for candidatura in candidatos:
            registro = candidatura.registro_padron
            if registro.pk in usados or (registro.sede_id and not registro.turno_cursada_id) or (registro.turno_cursada_id and registro.turno_cursada.se_superpone_con(turno)):
                continue
            if es_candidato_electoral(registro) or registro.sede_id == _sede_electoral_actual(registro):
                continue
            mesa_origen = registro.asignacion_mesa.mesa
            if mesa_origen.eleccion_claustro_departamento_id != mesa.eleccion_claustro_departamento_id:
                continue
            if not EleccionClaustroDepartamentoSede.objects.filter(
                eleccion_claustro_departamento=mesa.eleccion_claustro_departamento,
                sede=mesa.sede,
            ).exists():
                continue
            propuestas.append({
                "registro": registro,
                "candidatura": candidatura,
                "mesa_origen": mesa_origen,
                "mesa_destino": mesa,
                "turno": turno,
                "sede_origen": registro.asignacion_sede_padron.sede,
                "sede_destino": mesa.sede,
                "electores_mesa_origen": AsignacionMesa.objects.filter(mesa=mesa_origen).count(),
            })
            usados.add(registro.pk)
            propuestos_por_plaza[(mesa.pk, turno.pk)] += 1
            break
    return propuestas


@transaction.atomic
def confirmar_cambio_sede_para_autoridad(registro, sede_destino, usuario, *, mesa=None, turno=None):
    """Confirma un destino laboral; conserva sede y mesa de votación."""
    from apps.autoridades.distribucion import bloquear_edicion, configuracion_actual, _auditar
    claustro = registro.eleccion_claustro_departamento.eleccion_claustro
    bloquear_edicion(claustro)
    opciones = configuracion_actual(claustro)
    if opciones.modo != "nomina" or not opciones.permitir_cambio_sede:
        raise ValidationError("Los cambios de sede no están habilitados para este claustro.")
    if registro.sede_id == _sede_electoral_actual(registro):
        raise ValidationError("No se puede trasladar a quien cursa en su sede electoral de origen.")
    if mesa is None or turno is None or mesa.sede_id != sede_destino.pk:
        raise ValidationError("Indicá la mesa y el turno de trabajo a cubrir.")
    config = claustro.turnos_autoridad.filter(turno=turno).first()
    ocupadas = AsignacionAutoridad.objects.filter(mesa=mesa, turno=turno, tipo="titular", estado="asignada").count()
    if not config or ocupadas >= config.titulares_por_mesa:
        raise ValidationError("La mesa y el turno ya no tienen una vacante titular.")
    propuestas = proponer_cambios_sede(claustro, [(mesa, turno)])
    if not any(p["registro"].pk == registro.pk for p in propuestas):
        raise ValidationError("La propuesta ya no es válida; actualizá la cobertura.")
    candidatura = CandidaturaAutoridad.objects.get(registro_padron=registro)
    candidatura.mesa_traslado = mesa
    candidatura.turno_traslado = turno
    candidatura.save(update_fields=("mesa_traslado", "turno_traslado"))
    resumen = redistribuir_autoridades(claustro, usuario)
    if not AsignacionAutoridad.objects.filter(registro_padron=registro, mesa=mesa, turno=turno, tipo="titular").exists():
        raise ValidationError("El traslado no cubrió la vacante; no se aplicó ningún cambio.")
    _auditar(claustro, usuario, "autoridades.traslado_laboral", {
        "registro": registro.pk, "sede_origen": _sede_electoral_actual(registro),
        "sede_destino": sede_destino.pk, "mesa": mesa.pk, "turno": turno.pk,
    })
    return resumen


@transaction.atomic
def responder_asignacion(asignacion):
    """Registra únicamente el rechazo; la asignación rige sin aceptación previa."""
    from apps.usuarios.models import AsignacionRol, PerfilUsuario

    eleccion = Eleccion.objects.select_for_update().get(pk=asignacion.registro_padron.eleccion_id)
    if eleccion.estado == Eleccion.Estado.FINALIZADA:
        raise ValidationError("La elección está cerrada; no se puede informar una ausencia.")
    actual = AsignacionAutoridad.objects.select_for_update().get(pk=asignacion.pk)
    if actual.estado == AsignacionAutoridad.Estado.RECHAZADA:
        return
    asignacion.estado = AsignacionAutoridad.Estado.RECHAZADA
    asignacion.respondida_en = timezone.now()
    asignacion.save(update_fields=("estado", "respondida_en"))
    if asignacion.candidatura_id:
        asignacion.candidatura.excluida = True
        asignacion.candidatura.save(update_fields=("excluida",))
    perfil = PerfilUsuario.objects.filter(elector=asignacion.registro_padron.elector).first()
    if perfil:
        AsignacionRol.objects.filter(
            usuario=perfil.usuario,
            rol=AsignacionRol.Rol.AUTORIDAD_MESA,
            eleccion=asignacion.registro_padron.eleccion,
            mesa=asignacion.mesa,
        ).delete()
    from apps.autoridades.distribucion import _auditar
    _auditar(asignacion.mesa.eleccion_claustro_departamento.eleccion_claustro,
             perfil.usuario if perfil else None, "autoridades.ausencia_informada",
             {"asignacion": asignacion.pk, "registro": asignacion.registro_padron_id})


# La importación solo identifica electores; los datos personales siempre salen del padrón.
def validar_csv_autoridades(contenido, eleccion_claustro, nombre_archivo=""):
    from apps.autoridades.distribucion import es_candidato_electoral
    try:
        filas = leer_filas_autoridades(contenido, nombre_archivo)
    except ValueError as error:
        return [], [(None, str(error))]
    if not filas:
        return [], [(None, "El archivo no contiene filas de autoridades.")]
    encabezados = {str(c).strip().casefold(): c for c in filas[0]}
    campo_documento = next((encabezados[n] for n in ("documento", "dni", "cuil") if n in encabezados), None)
    campo_tipo = next((encabezados[n] for n in ("tipo documento", "tipo_documento") if n in encabezados), None)
    campo_legajo = encabezados.get("legajo")
    if not campo_documento and not campo_legajo:
        return [], [(None, "El archivo debe incluir Documento (DNI/CUIL) o Legajo.")]
    normalizadas, errores, vistos, electores_vistos = [], [], set(), set()
    for numero, fila in enumerate(filas, start=2):
        doc = (fila.get(campo_documento) or "").strip() if campo_documento else ""
        legajo = (fila.get(campo_legajo) or "").strip() if campo_legajo else ""
        tipo = (fila.get(campo_tipo) or "DNI").strip() if campo_tipo else ("CUIL" if "cuil" in encabezados else "DNI")
        clave = (tipo.casefold(), doc, legajo)
        if not doc and not legajo:
            errores.append((numero, "Debe informarse Documento o Legajo."))
            continue
        clave_repetida = clave in vistos
        if clave_repetida:
            errores.append((numero, "El elector está repetido en el archivo."))
        vistos.add(clave)
        consulta = RegistroPadron.objects.filter(
            eleccion=eleccion_claustro.eleccion,
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            activo=True,
        )
        if doc:
            consulta = consulta.filter(elector__tipo_documento__iexact=tipo, elector__dni=doc)
        if legajo:
            consulta = consulta.filter(elector__legajo=legajo)
        coincidencias = consulta.values("elector_id").distinct().count()
        if coincidencias == 0:
            errores.append((numero, "El elector no pertenece al padron activo de este claustro."))
        elif coincidencias > 1:
            errores.append((numero, "Los identificadores coinciden con más de un elector del padrón."))
        else:
            registro = consulta.select_related("elector").first()
            if registro.elector_id in electores_vistos and not clave_repetida:
                errores.append((numero, "El elector está repetido en el archivo."))
            electores_vistos.add(registro.elector_id)
            if es_candidato_electoral(registro):
                errores.append((numero, "Un candidato electoral no puede ser autoridad de mesa."))
        normalizadas.append({"documento": doc, "dni": doc, "tipo_documento": tipo, "legajo": legajo})
    return normalizadas, errores


@transaction.atomic
def importar_autoridades(contenido, eleccion_claustro, usuario, nombre_archivo="", *, distribuir_al_cargar=False):
    from apps.autoridades.distribucion import bloquear_edicion, configuracion_actual
    try:
        bloquear_edicion(eleccion_claustro)
    except ValidationError as error:
        return 0, 0, [(None, error.messages[0])], None
    if configuracion_actual(eleccion_claustro).modo != "nomina":
        return 0, 0, [(None, "La importación de nómina requiere el modo nómina común.")], None
    if RegistroPadron.objects.filter(eleccion=eleccion_claustro.eleccion, qr_generado_en__isnull=False).exists():
        return 0, 0, [(None, "La nómina no puede cambiarse después de emitir el padrón imprimible.")], None
    filas, errores = validar_csv_autoridades(contenido, eleccion_claustro, nombre_archivo)
    if errores:
        return 0, 0, errores, None
    creadas = 0
    ya_cargadas = 0
    for fila in filas:
        consulta = RegistroPadron.objects.filter(
            eleccion=eleccion_claustro.eleccion,
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            activo=True,
        )
        if fila["documento"]:
            consulta = consulta.filter(elector__tipo_documento__iexact=fila["tipo_documento"], elector__dni=fila["documento"])
        if fila["legajo"]:
            consulta = consulta.filter(elector__legajo=fila["legajo"])
        creada_para_persona = False
        for registro in consulta:
            _, creada = CandidaturaAutoridad.objects.get_or_create(
                registro_padron=registro,
                defaults={"cargada_por": usuario},
            )
            creada_para_persona |= creada
        creadas += int(creada_para_persona)
        ya_cargadas += int(not creada_para_persona)
    distribucion_pendiente = None
    if creadas and not distribuir_al_cargar:
        distribucion_pendiente = "Revisá y confirmá la distribución de la nómina desde autoridades."
    if distribuir_al_cargar and creadas and Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro).exists():
        try:
            redistribuir_autoridades(eleccion_claustro, usuario)
        except ValidationError as error:
            distribucion_pendiente = error.messages[0]
    return creadas, ya_cargadas, [], distribucion_pendiente
