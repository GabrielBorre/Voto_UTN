import zxingcpp
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.asistencia.models import RegistroParticipacion
from apps.asistencia.services import ServicioRegistroParticipacion
from apps.auditoria.services import registrar_evento

from .models import JustificativoAusencia

Validacion = JustificativoAusencia.ValidacionComprobante
EXTENSIONES_IMAGEN = (".jpg", ".jpeg", ".png")


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
