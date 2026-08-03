import base64
import hashlib
import hmac
import struct
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from apps.elecciones.models import Eleccion, RegistroPadron
from apps.usuarios.permisos import puede_registrar_participacion
from .models import RegistroParticipacion


@dataclass(frozen=True)
class ResultadoParticipacion:
    creados: list[str]
    ya_registrados: list[str]
    invalidos: list[str]


class ServicioRegistroParticipacion:
    VERSION_QR = "v1"
    LONGITUD_FIRMA = 16

    @classmethod
    def generar_codigo_qr(cls, *, eleccion_id, mesa_numero, identificador_qr):
        datos = struct.pack(">HH", eleccion_id, mesa_numero) + uuid.UUID(str(identificador_qr)).bytes
        firma = hmac.new(settings.CLAVE_FIRMA_QR.encode("utf-8"), datos, hashlib.sha256).digest()[:cls.LONGITUD_FIRMA]
        return f"{cls.VERSION_QR}.{base64.urlsafe_b64encode(datos + firma).decode('ascii').rstrip('=')}"

    @classmethod
    def parsear_codigo_qr(cls, codigo):
        if not isinstance(codigo, str) or not codigo.startswith(f"{cls.VERSION_QR}."):
            return None
        contenido = codigo[len(cls.VERSION_QR) + 1:].strip()
        try:
            binario = base64.urlsafe_b64decode(contenido + "=" * (-len(contenido) % 4))
        except Exception:
            return None
        if len(binario) != 20 + cls.LONGITUD_FIRMA:
            return None
        datos, firma = binario[:-cls.LONGITUD_FIRMA], binario[-cls.LONGITUD_FIRMA:]
        esperada = hmac.new(settings.CLAVE_FIRMA_QR.encode("utf-8"), datos, hashlib.sha256).digest()[:cls.LONGITUD_FIRMA]
        if not hmac.compare_digest(firma, esperada):
            return None
        eleccion_id, mesa_numero = struct.unpack(">HH", datos[:4])
        return eleccion_id, mesa_numero, uuid.UUID(bytes=datos[4:]).hex

    @classmethod
    def registrar_lote(cls, *, eleccion: Eleccion, codigos_qr: list, usuario) -> ResultadoParticipacion:
        codigos = list(dict.fromkeys(codigo.strip() for codigo in codigos_qr if isinstance(codigo, str) and codigo.strip()))
        parseados, invalidos = [], []
        for codigo in codigos:
            parseado = cls.parsear_codigo_qr(codigo)
            if parseado is None or parseado[0] != eleccion.id:
                invalidos.append(codigo)
            else:
                parseados.append((codigo, parseado[1], parseado[2]))

        identificadores = [identificador for _, _, identificador in parseados]
        padrones = {
            padron.identificador_qr.hex: padron
            for padron in RegistroPadron.objects.select_related("asignacion_mesa__mesa").filter(
                eleccion=eleccion,
                activo=True,
                identificador_qr__in=identificadores,
            )
        }
        validos = []
        for codigo, mesa_numero, identificador in parseados:
            padron = padrones.get(identificador)
            mesa = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
            if padron is None or mesa is None or mesa.numero != mesa_numero or not puede_registrar_participacion(usuario, eleccion, mesa):
                invalidos.append(codigo)
            else:
                validos.append((identificador, padron, mesa))

        existentes = set(RegistroParticipacion.objects.filter(registro_padron__identificador_qr__in=[item[1].identificador_qr for item in validos]).values_list("registro_padron__identificador_qr", flat=True))
        nuevos = [item for item in validos if item[1].identificador_qr not in existentes]
        with transaction.atomic():
            RegistroParticipacion.objects.bulk_create([
                RegistroParticipacion(registro_padron=padron, mesa=mesa, registrada_por=usuario, metodo=RegistroParticipacion.Metodo.QR)
                for _, padron, mesa in nuevos
            ], ignore_conflicts=True)
        return ResultadoParticipacion(
            creados=[identificador for identificador, _, _ in nuevos],
            ya_registrados=[str(identificador) for identificador in existentes],
            invalidos=invalidos,
        )

    @classmethod
    def registrar_manual(cls, *, eleccion: Eleccion, mesa_numero: int, dni: str, usuario) -> ResultadoParticipacion:
        padron = RegistroPadron.objects.select_related("asignacion_mesa__mesa").filter(eleccion=eleccion, activo=True, elector__dni=str(dni).strip()).first()
        mesa = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
        if padron is None or mesa is None or mesa.numero != mesa_numero or not puede_registrar_participacion(usuario, eleccion, mesa):
            return ResultadoParticipacion([], [], ["Elector no disponible para la mesa indicada."])
        if RegistroParticipacion.objects.filter(registro_padron=padron).exists():
            return ResultadoParticipacion([], [padron.identificador_qr.hex], [])
        RegistroParticipacion.objects.create(registro_padron=padron, mesa=mesa, registrada_por=usuario, metodo=RegistroParticipacion.Metodo.MANUAL)
        return ResultadoParticipacion([padron.identificador_qr.hex], [], [])
