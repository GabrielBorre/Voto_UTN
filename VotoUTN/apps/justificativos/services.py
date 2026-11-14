from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.justificativos.models import JustificativoAusencia


@transaction.atomic
def resolver_justificativo(justificativo, *, estado, observacion, usuario):
    from apps.elecciones.models import Eleccion

    eleccion = Eleccion.objects.select_for_update().get(pk=justificativo.registro_padron.eleccion_id)
    actual = JustificativoAusencia.objects.select_for_update().get(pk=justificativo.pk)
    pendiente = actual.estado == JustificativoAusencia.Estado.PENDIENTE
    if (estado == JustificativoAusencia.Estado.APROBADO
            and actual.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD
            and (eleccion.estado != Eleccion.Estado.PUBLICADA or not eleccion.autoridades_confirmadas_en)):
        raise ValidationError("Una ausencia como autoridad solo puede aprobarse tras confirmar las autoridades y mientras la elección está publicada.")
    if estado == JustificativoAusencia.Estado.APROBADO and actual.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD:
        from apps.padron.models import RegistroPadron
        if RegistroPadron.objects.filter(eleccion=eleccion, qr_generado_en__isnull=False).exists():
            raise ValidationError("No se pueden modificar autoridades después de emitir el padrón con QR.")
    actual.estado = estado
    actual.observacion_resolucion = observacion
    actual.resuelta_por = usuario
    actual.resuelta_en = timezone.now()
    actual.full_clean()
    actual.save()
    if (estado == JustificativoAusencia.Estado.APROBADO
            and actual.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD
            and actual.reemplazo_procesado_en is None):
        from apps.autoridades.models import AsignacionAutoridad
        from apps.autoridades.services import responder_asignacion

        asignacion = AsignacionAutoridad.objects.select_for_update().filter(
            registro_padron=actual.registro_padron,
        ).first()
        if asignacion is not None:
            if asignacion.estado == AsignacionAutoridad.Estado.ASIGNADA:
                responder_asignacion(asignacion)
                asignacion.refresh_from_db()
                from apps.autoridades.retorno_votacion import intentar_restituir_mesa
                intentar_restituir_mesa(asignacion, usuario)
        actual.reemplazo_procesado_en = timezone.now()
        actual.save(update_fields=("reemplazo_procesado_en",))
    justificativo.refresh_from_db()
    return pendiente


import zxingcpp
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.auditoria.services import registrar_evento

from .models import JustificativoAusencia

Validacion = JustificativoAusencia.ValidacionComprobante
EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png")


def justificativos_electorales_para_registro(*, registro_id, elector_id, eleccion_id):
    """Una justificación de ausencia cubre a la persona; un reclamo conserva su mesa."""
    return JustificativoAusencia.objects.filter(
        Q(registro_padron_id=registro_id)
        | Q(
            reclamo_participacion=False,
            registro_padron__elector_id=elector_id,
            registro_padron__eleccion_id=eleccion_id,
        ),
        ausencia=JustificativoAusencia.Ausencia.VOTAR,
    )


def registros_ausentes_de_persona(registro_padron):
    from apps.padron.models import RegistroPadron

    return RegistroPadron.objects.filter(
        elector_id=registro_padron.elector_id,
        eleccion_id=registro_padron.eleccion_id,
        activo=True,
        participaciones__isnull=False,
    ).distinct()


def puede_presentar_justificativo_electoral(registro_padron, momento=None):
    momento = momento or timezone.now()
    eleccion = registro_padron.eleccion
    habilitada_en = eleccion.justificacion_electores_habilitada_en
    if habilitada_en is None or habilitada_en > momento:
        return False
    if (
        eleccion.fecha_limite_justificacion_electores
        and timezone.localdate(momento) > eleccion.fecha_limite_justificacion_electores
    ):
        return False
    return registros_ausentes_de_persona(registro_padron).exists()


def estado_justificativo_electoral(justificativo):
    if justificativo.estado == JustificativoAusencia.Estado.PENDIENTE:
        return "Justificativo Pendiente de Revisión", "warn"
    if justificativo.estado == JustificativoAusencia.Estado.APROBADO:
        return "Inasistencia Justificada", "ok"
    if justificativo.estado == JustificativoAusencia.Estado.RECHAZADO:
        return "Infractor - Justificación Rechazada", "danger"
    raise ValueError(f"Estado de justificativo electoral desconocido: {justificativo.estado}")


def _leer_codigos_qr(archivo):
    archivo.open("rb")
    try:
        with Image.open(archivo) as imagen:
            imagen = ImageOps.exif_transpose(imagen).convert("RGB")
            resultados = zxingcpp.read_barcodes(imagen, formats=zxingcpp.BarcodeFormat.QRCode)
    finally:
        archivo.close()
    return [resultado.text for resultado in resultados if resultado.text]


def evaluar_comprobante(justificativo):
    """Devuelve (estado, detalle) de la validación del troquel adjunto en un reclamo de participación."""
    if not justificativo.reclamo_participacion:
        return Validacion.NO_APLICA, ""
    if not justificativo.documento:
        return Validacion.SIN_COMPROBANTE, "El elector declaró que perdió el comprobante. Verificá el padrón manualmente."
    if not justificativo.documento.name.lower().endswith(EXTENSIONES_IMAGEN):
        return Validacion.NO_PROCESABLE, "El comprobante no es una imagen JPG o PNG; revisalo manualmente."
    try:
        codigos = _leer_codigos_qr(justificativo.documento)
    except (UnidentifiedImageError, OSError, ValueError):
        return Validacion.NO_DETECTADO, "No se pudo leer la imagen adjunta."
    if not codigos:
        return Validacion.NO_DETECTADO, "No se encontró un código QR legible en la imagen."

    registro = justificativo.registro_padron
    motivos = []
    for codigo in codigos:
        datos = ServicioRegistroParticipacion.parsear_codigo_qr(codigo)
        if datos is None:
            motivos.append("El QR no es un comprobante firmado por el sistema.")
            continue
        eleccion_id, mesa_numero, identificador = datos
        if eleccion_id != registro.eleccion_id:
            motivos.append("El QR corresponde a otra elección.")
        elif not registro.identificador_qr or identificador != registro.identificador_qr.upper():
            motivos.append("El QR corresponde a otro elector.")
        else:
            return Validacion.VALIDO, f"El QR corresponde al elector y a la mesa {mesa_numero}."
    return Validacion.INVALIDO, " ".join(dict.fromkeys(motivos))


def validar_comprobante(justificativo, *, guardar=True):
    estado, detalle = evaluar_comprobante(justificativo)
    justificativo.validacion_comprobante = estado
    justificativo.detalle_validacion_comprobante = detalle
    justificativo.comprobante_validado_en = timezone.now() if estado != Validacion.NO_APLICA else None
    if guardar:
        justificativo.save(update_fields=(
            "validacion_comprobante", "detalle_validacion_comprobante", "comprobante_validado_en",
        ))
    return estado


def anular_participacion_por_reclamo(justificativo, *, usuario, request=None):
    """Elimina la ausencia registrada guardando una copia en el justificativo. Ejecutar dentro de una transacción."""
    participacion = (
        RegistroParticipacion.objects.select_for_update()
        .filter(registro_padron_id=justificativo.registro_padron_id)
        .first()
    )
    if participacion is None:
        return False
    respaldo = {
        "id": participacion.pk,
        "registro_padron_id": participacion.registro_padron_id,
        "mesa_id": participacion.mesa_id,
        "registrada_por_id": participacion.registrada_por_id,
        "registrada_en": participacion.registrada_en.isoformat(),
        "metodo": participacion.metodo,
    }
    participacion.delete()
    justificativo.respaldo_participacion = respaldo
    justificativo.participacion_anulada_en = timezone.now()
    justificativo.save(update_fields=("respaldo_participacion", "participacion_anulada_en"))
    registrar_evento(
        accion="participacion.anulada_por_reclamo",
        entidad="RegistroParticipacion",
        entidad_id=respaldo["id"],
        eleccion=justificativo.registro_padron.eleccion,
        usuario=usuario,
        request=request,
        datos_anteriores=respaldo,
        datos_nuevos={"justificativo_id": justificativo.pk},
    )
    return True


def restaurar_participacion_anulada(justificativo, *, usuario, request=None):
    """Revierte la anulación si la resolución aprobada de un reclamo se cambia a rechazada."""
    respaldo = justificativo.respaldo_participacion
    if not respaldo or justificativo.participacion_anulada_en is None:
        return False
    if RegistroParticipacion.objects.filter(registro_padron_id=justificativo.registro_padron_id).exists():
        restaurada = None
    else:
        restaurada = RegistroParticipacion.objects.create(
            registro_padron_id=respaldo["registro_padron_id"],
            mesa_id=respaldo["mesa_id"],
            registrada_por_id=respaldo["registrada_por_id"],
            metodo=respaldo["metodo"],
        )
        # registrada_en es auto_now_add: se restaura el instante original con un update.
        RegistroParticipacion.objects.filter(pk=restaurada.pk).update(registrada_en=respaldo["registrada_en"])
    justificativo.participacion_anulada_en = None
    justificativo.save(update_fields=("participacion_anulada_en",))
    registrar_evento(
        accion="participacion.restaurada_por_reclamo",
        entidad="RegistroParticipacion",
        entidad_id=restaurada.pk if restaurada else respaldo["id"],
        eleccion=justificativo.registro_padron.eleccion,
        usuario=usuario,
        request=request,
        datos_anteriores={"justificativo_id": justificativo.pk},
        datos_nuevos=respaldo,
    )
    return restaurada is not None
