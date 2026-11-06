import hashlib
import hmac
from dataclasses import dataclass, field

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditoria.services import registrar_evento
from apps.elecciones.models import Eleccion
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.usuarios.permisos import puede_registrar_participacion
from .models import RegistroParticipacion


@dataclass(frozen=True)
class ResultadoParticipacion:
    creados: list[str]
    ya_registrados: list[str]
    invalidos: list[str]
    invalidos_otra_eleccion: list[str]
    mesa_numero: int | None = None
    departamento_codigo: str | None = None
    invalidos_otra_mesa: list[str] = field(default_factory=list)


class ErrorEscaneoMesa(Exception):
    """Regla de escaneo de mesa incumplida; `estado_http` orienta la respuesta de la API."""

    def __init__(self, mensaje, estado_http=409):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado_http = estado_http


class ServicioRegistroParticipacion:
    VERSION_QR = "v1"
    VERSION_QR_MESA = "M1"
    LONGITUD_IDENTIFICADOR = 8
    LONGITUD_FIRMA = 4
    ANCHO_BASE36_ELECCION = 2
    ANCHO_BASE36_MESA = 2
    ALFABETO_QR = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    @classmethod
    def _to_base36(cls, valor: int, ancho: int):
        if valor < 0:
            raise ValueError("El valor no puede ser negativo.")
        caracteres = []
        while valor:
            valor, resto = divmod(valor, 36)
            caracteres.append(cls.ALFABETO_QR[resto])
        texto = "".join(reversed(caracteres or ["0"]))
        return texto.rjust(ancho, "0")

    @classmethod
    def _from_base36(cls, texto: str):
        return int(texto, 36)

    @classmethod
    def _firma_corta(cls, cuerpo: str):
        digest = hmac.new(
            settings.CLAVE_FIRMA_QR.encode("utf-8"),
            cuerpo.encode("ascii"),
            hashlib.sha256,
        ).digest()
        valor = int.from_bytes(digest[:2], "big")
        return cls._to_base36(valor, cls.LONGITUD_FIRMA)

    @classmethod
    def generar_codigo_qr(cls, *, eleccion_id, mesa_numero, identificador_qr):
        identificador = str(identificador_qr).strip().upper()
        if not identificador or len(identificador) != cls.LONGITUD_IDENTIFICADOR or not identificador.isalnum():
            raise ValueError("El identificador QR debe ser alfanumerico y de longitud 8.")
        eleccion_token = cls._to_base36(int(eleccion_id), cls.ANCHO_BASE36_ELECCION)
        cuerpo = (
            eleccion_token
            + cls._to_base36(int(mesa_numero), cls.ANCHO_BASE36_MESA)
            + identificador
        )
        firma = cls._firma_corta(cuerpo)
        return f"{cls.VERSION_QR.upper()}.{cuerpo}{firma}"

    @classmethod
    def parsear_codigo_qr(cls, codigo):
        if not isinstance(codigo, str):
            return None
        version, separador, contenido = codigo.strip().upper().partition(".")
        if separador != "." or version != cls.VERSION_QR.upper():
            return None

        ancho_eleccion = len(contenido) - (
            cls.ANCHO_BASE36_MESA
            + cls.LONGITUD_IDENTIFICADOR
            + cls.LONGITUD_FIRMA
        )
        if ancho_eleccion < cls.ANCHO_BASE36_ELECCION or not contenido.isalnum():
            return None

        cuerpo = contenido[:-cls.LONGITUD_FIRMA]
        firma = contenido[-cls.LONGITUD_FIRMA:]
        esperada = cls._firma_corta(cuerpo)
        if not hmac.compare_digest(firma, esperada):
            return None

        eleccion_token = cuerpo[:ancho_eleccion]
        mesa_token = cuerpo[
            ancho_eleccion: ancho_eleccion + cls.ANCHO_BASE36_MESA
        ]
        identificador = cuerpo[ancho_eleccion + cls.ANCHO_BASE36_MESA:]
        try:
            eleccion_id = cls._from_base36(eleccion_token)
            mesa_numero = cls._from_base36(mesa_token)
        except ValueError:
            return None
        return eleccion_id, mesa_numero, identificador

    @classmethod
    def generar_codigo_qr_mesa(cls, *, eleccion_id, mesa_numero):
        cuerpo = cls._to_base36(int(eleccion_id), cls.ANCHO_BASE36_ELECCION) + cls._to_base36(int(mesa_numero), cls.ANCHO_BASE36_MESA)
        # El prefijo de dominio evita que una firma de mesa se reutilice con otro tipo de QR.
        firma = cls._firma_corta(f"{cls.VERSION_QR_MESA}{cuerpo}")
        return f"{cls.VERSION_QR_MESA}.{cuerpo}{firma}"

    @classmethod
    def parsear_codigo_qr_mesa(cls, codigo):
        if not isinstance(codigo, str):
            return None
        version, separador, contenido = codigo.strip().upper().partition(".")
        if separador != "." or version != cls.VERSION_QR_MESA:
            return None
        ancho_eleccion = len(contenido) - cls.ANCHO_BASE36_MESA - cls.LONGITUD_FIRMA
        if ancho_eleccion < cls.ANCHO_BASE36_ELECCION or not contenido.isalnum():
            return None
        largo_cuerpo = ancho_eleccion + cls.ANCHO_BASE36_MESA
        cuerpo, firma = contenido[:largo_cuerpo], contenido[largo_cuerpo:]
        if not hmac.compare_digest(firma, cls._firma_corta(f"{version}{cuerpo}")):
            return None
        return cls._from_base36(cuerpo[:ancho_eleccion]), cls._from_base36(cuerpo[ancho_eleccion:])

    @staticmethod
    def _mesas_de(eleccion):
        return Mesa.objects.select_related(
            "sede",
            "eleccion_claustro_departamento__departamento",
            "eleccion_claustro_departamento__eleccion_claustro__claustro",
        ).filter(eleccion=eleccion)

    @classmethod
    def resolver_mesa(cls, *, eleccion: Eleccion, usuario, codigo_qr=None, codigo_mesa=None) -> Mesa:
        """Obtiene la mesa desde un QR firmado o desde el codigo escrito a mano, validando alcance del usuario."""
        if codigo_qr:
            parseado = cls.parsear_codigo_qr_mesa(codigo_qr)
            if parseado is None:
                raise ErrorEscaneoMesa("El QR no es un QR de mesa válido.", 400)
            if parseado[0] != eleccion.id:
                raise ErrorEscaneoMesa("El QR de mesa pertenece a otra elección.", 400)
            mesa = cls._mesas_de(eleccion).filter(numero=parseado[1]).first()
        else:
            texto = (codigo_mesa or "").strip().upper()
            departamento, separador, numero = texto.rpartition("-")
            if not numero.isdigit():
                raise ErrorEscaneoMesa("Ingresá el código con el formato CODIGO_DEPARTAMENTO-NUMERO_DE_MESA.", 400)
            mesa = cls._mesas_de(eleccion).filter(numero=int(numero)).first()
            if mesa is not None and mesa.codigo.upper() != (f"{departamento}-{int(numero):03d}" if separador else f"{int(numero):03d}"):
                mesa = None
        if mesa is None:
            raise ErrorEscaneoMesa("No existe una mesa con ese código en esta elección.", 404)
        if not puede_registrar_participacion(usuario, eleccion, mesa):
            raise ErrorEscaneoMesa("No tenés permisos para registrar participación en esta mesa.", 403)
        return mesa

    @staticmethod
    def describir_mesa(mesa: Mesa) -> dict:
        configuracion = mesa.eleccion_claustro_departamento
        departamento = configuracion.departamento if configuracion else None
        claustro = configuracion.eleccion_claustro.claustro if configuracion else None
        return {
            "codigo": mesa.codigo,
            "numero": mesa.numero,
            "departamento_codigo": departamento.codigo if departamento else None,
            "departamento": departamento.nombre if departamento else None,
            "claustro": claustro.nombre if claustro else None,
            "sede": mesa.sede.nombre if mesa.sede_id else None,
            "estado": mesa.estado_escaneo,
            "estado_display": mesa.get_estado_escaneo_display(),
            "electores": mesa.asignaciones_padron.filter(registro_padron__activo=True).count(),
            "registrados": mesa.participaciones.filter(registro_padron__activo=True).count(),
        }

    @classmethod
    def iniciar_escaneo_mesa(cls, *, mesa: Mesa, usuario) -> Mesa:
        with transaction.atomic():
            mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
            if mesa.estado_escaneo == Mesa.EstadoEscaneo.PROCESADA:
                raise ErrorEscaneoMesa("La mesa ya fue procesada.")
            if mesa.estado_escaneo == Mesa.EstadoEscaneo.PENDIENTE:
                mesa.estado_escaneo = Mesa.EstadoEscaneo.EN_PROCESO
                mesa.escaneo_iniciado_en = timezone.now()
                mesa.save(update_fields=["estado_escaneo", "escaneo_iniciado_en"])
                registrar_evento(
                    accion="mesa.escaneo_iniciado",
                    entidad="Mesa",
                    entidad_id=mesa.pk,
                    eleccion=mesa.eleccion,
                    usuario=usuario,
                    datos_nuevos={"estado": mesa.estado_escaneo},
                )
        return mesa

    @classmethod
    def finalizar_escaneo_mesa(cls, *, mesa: Mesa, usuario, confirmar_sin_inasistencias=False) -> Mesa:
        with transaction.atomic():
            mesa = Mesa.objects.select_for_update().get(pk=mesa.pk)
            if mesa.estado_escaneo != Mesa.EstadoEscaneo.EN_PROCESO:
                raise ErrorEscaneoMesa("Solo se puede registrar una mesa cuyo escaneo está en proceso.")
            sin_registros = not mesa.participaciones.exists()
            if sin_registros and not confirmar_sin_inasistencias:
                raise ErrorEscaneoMesa("Confirmá que en esta mesa no hubo inasistencias.", 422)
            mesa.estado_escaneo = Mesa.EstadoEscaneo.PROCESADA
            mesa.procesada_en = timezone.now()
            mesa.save(update_fields=["estado_escaneo", "procesada_en"])
            registrar_evento(
                accion="mesa.procesada",
                entidad="Mesa",
                entidad_id=mesa.pk,
                eleccion=mesa.eleccion,
                usuario=usuario,
                datos_nuevos={"estado": mesa.estado_escaneo, "sin_inasistencias": sin_registros},
            )
        return mesa

    @classmethod
    def registrar_lote(cls, *, eleccion: Eleccion, mesa: Mesa, codigos_qr: list, usuario) -> ResultadoParticipacion:
        if mesa.eleccion_id != eleccion.id or mesa.estado_escaneo != Mesa.EstadoEscaneo.EN_PROCESO:
            raise ErrorEscaneoMesa("Primero escaneá el QR de la mesa y comenzá su escaneo.")
        codigos = list(dict.fromkeys(codigo.strip() for codigo in codigos_qr if isinstance(codigo, str) and codigo.strip()))
        parseados, invalidos, invalidos_otra_eleccion, invalidos_otra_mesa = [], [], [], []
        for codigo in codigos:
            parseado = cls.parsear_codigo_qr(codigo)
            if parseado is None:
                invalidos.append(codigo)
            elif parseado[0] != eleccion.id:
                invalidos.append(codigo)
                invalidos_otra_eleccion.append(codigo)
            elif parseado[1] != mesa.numero:
                invalidos.append(codigo)
                invalidos_otra_mesa.append(codigo)
            else:
                parseados.append((codigo, parseado[1], parseado[2]))

        identificadores = [identificador for _, _, identificador in parseados]
        padrones = {
            padron.identificador_qr: padron
            for padron in RegistroPadron.objects.select_related(
                "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento"
            ).filter(
            eleccion=eleccion,
            activo=True,
            identificador_qr__in=identificadores,
            )
        }
        validos = []
        for codigo, mesa_numero, identificador in parseados:
            padron = padrones.get(identificador)
            mesa_padron = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
            if padron is None or mesa_padron is None or mesa_padron.pk != mesa.pk or not puede_registrar_participacion(usuario, eleccion, mesa):
                invalidos.append(codigo)
                if mesa_padron is not None and mesa_padron.pk != mesa.pk:
                    invalidos_otra_mesa.append(codigo)
            else:
                validos.append((identificador, padron, mesa))

        existentes = set(RegistroParticipacion.objects.filter(registro_padron__identificador_qr__in=[item[1].identificador_qr for item in validos]).values_list("registro_padron__identificador_qr", flat=True))
        nuevos = [item for item in validos if item[1].identificador_qr not in existentes]
        creados_reales = []
        with transaction.atomic():
            for _, padron, mesa in nuevos:
                try:
                    with transaction.atomic():
                        participacion = RegistroParticipacion.objects.create(
                            registro_padron=padron,
                            mesa=mesa,
                            registrada_por=usuario,
                            metodo=RegistroParticipacion.Metodo.QR,
                        )
                except IntegrityError:
                    existentes.add(padron.identificador_qr)
                    continue
                creados_reales.append((padron.identificador_qr, participacion))
                registrar_evento(
                    accion="participacion.registrada_qr",
                    entidad="RegistroParticipacion",
                    entidad_id=participacion.pk,
                    eleccion=eleccion,
                    usuario=usuario,
                    datos_nuevos={
                        "registro_padron_id": participacion.registro_padron_id,
                        "mesa_id": participacion.mesa_id,
                        "metodo": participacion.metodo,
                    },
                )

        departamento_codigo = None
        if mesa.eleccion_claustro_departamento_id:
            departamento = mesa.eleccion_claustro_departamento.departamento
            departamento_codigo = departamento.codigo if departamento else None

        return ResultadoParticipacion(
            creados=[identificador for identificador, _ in creados_reales],
            ya_registrados=[str(identificador) for identificador in existentes],
            invalidos=invalidos,
            invalidos_otra_eleccion=invalidos_otra_eleccion,
            mesa_numero=mesa.numero,
            departamento_codigo=departamento_codigo,
            invalidos_otra_mesa=invalidos_otra_mesa,
        )

    @classmethod
    def registrar_manual(cls, *, eleccion: Eleccion, mesa_numero: int, dni: str, usuario) -> ResultadoParticipacion:
        padron = RegistroPadron.objects.select_related(
            "asignacion_mesa__mesa__eleccion_claustro_departamento__departamento"
        ).filter(eleccion=eleccion, activo=True, elector__dni=str(dni).strip()).first()
        mesa = getattr(getattr(padron, "asignacion_mesa", None), "mesa", None)
        if padron is None or mesa is None or mesa.numero != mesa_numero or not puede_registrar_participacion(usuario, eleccion, mesa):
            return ResultadoParticipacion([], [], ["Elector no disponible para la mesa indicada."], [])
        if RegistroParticipacion.objects.filter(registro_padron=padron).exists():
            return ResultadoParticipacion(
                [],
                [padron.identificador_qr],
                [],
                [],
                mesa_numero=mesa.numero,
                departamento_codigo=mesa.eleccion_claustro_departamento.departamento.codigo if mesa.eleccion_claustro_departamento_id else None,
            )
        participacion = RegistroParticipacion.objects.create(registro_padron=padron, mesa=mesa, registrada_por=usuario, metodo=RegistroParticipacion.Metodo.MANUAL)
        registrar_evento(
            accion="participacion.registrada_manual",
            entidad="RegistroParticipacion",
            entidad_id=participacion.pk,
            eleccion=eleccion,
            usuario=usuario,
            datos_nuevos={
                "registro_padron_id": participacion.registro_padron_id,
                "mesa_id": participacion.mesa_id,
                "metodo": participacion.metodo,
            },
        )
        return ResultadoParticipacion(
            [padron.identificador_qr],
            [],
            [],
            [],
            mesa_numero=mesa.numero,
            departamento_codigo=mesa.eleccion_claustro_departamento.departamento.codigo if mesa.eleccion_claustro_departamento_id else None,
        )
