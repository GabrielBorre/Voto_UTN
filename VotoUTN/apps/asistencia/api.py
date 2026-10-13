from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_registrar_participacion
from rest_framework.exceptions import PermissionDenied
from .serializers import SerializadorCargaManualAsistencia, SerializadorEscaneoMesa, SerializadorLoteAsistencia
from .services import ErrorEscaneoMesa, ServicioRegistroParticipacion


def _respuesta_error(error: ErrorEscaneoMesa):
    return Response({"detail": error.mensaje}, status=error.estado_http)


class APIVistaAsistenciaLote(APIView):
    def post(self, request, eleccion_id):
        eleccion = get_object_or_404(Eleccion, pk=eleccion_id, habilitada=True)
        if not puede_registrar_participacion(request.user, eleccion):
            raise PermissionDenied("No tenés permisos para registrar participación en esta elección.")

        if "codigos_qr" in request.data:
            serializer = SerializadorLoteAsistencia(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                mesa = ServicioRegistroParticipacion.resolver_mesa(
                    eleccion=eleccion,
                    usuario=request.user,
                    codigo_mesa=serializer.validated_data["mesa_codigo"],
                )
                result = ServicioRegistroParticipacion.registrar_lote(
                    eleccion=eleccion,
                    mesa=mesa,
                    codigos_qr=serializer.validated_data["codigos_qr"],
                    usuario=request.user,
                )
            except ErrorEscaneoMesa as error:
                return _respuesta_error(error)
            recibidos = len(serializer.validated_data["codigos_qr"])
        else:
            serializer = SerializadorCargaManualAsistencia(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                mesa = ServicioRegistroParticipacion.resolver_mesa(
                    eleccion=eleccion,
                    usuario=request.user,
                    codigo_mesa=serializer.validated_data["mesa_codigo"],
                )
            except ErrorEscaneoMesa as error:
                return _respuesta_error(error)
            result = ServicioRegistroParticipacion.registrar_manual(
                eleccion=eleccion,
                mesa_numero=mesa.numero,
                dni=serializer.validated_data["dni"],
                usuario=request.user,
            )
            recibidos = 1

        return Response(
            {
                "creados": result.creados,
                "ya_registrados": result.ya_registrados,
                "invalidos": result.invalidos,
                "invalidos_otra_eleccion": result.invalidos_otra_eleccion,
                "invalidos_otra_mesa": result.invalidos_otra_mesa,
                "recibidos": recibidos,
                "mesa_numero": result.mesa_numero,
                "departamento_codigo": result.departamento_codigo,
            }
        )


class APIVistaEscaneoMesa(APIView):
    """Consulta, inicia y confirma el escaneo de una mesa; el estado solo cambia en el servidor."""

    def post(self, request, eleccion_id):
        eleccion = get_object_or_404(Eleccion, pk=eleccion_id, habilitada=True)
        if not puede_registrar_participacion(request.user, eleccion):
            raise PermissionDenied("No tenés permisos para registrar participación en esta elección.")
        serializer = SerializadorEscaneoMesa(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            mesa = ServicioRegistroParticipacion.resolver_mesa(
                eleccion=eleccion,
                usuario=request.user,
                codigo_qr=datos.get("codigo_qr"),
                codigo_mesa=datos.get("codigo_mesa"),
            )
            if datos["accion"] == "iniciar":
                mesa = ServicioRegistroParticipacion.iniciar_escaneo_mesa(mesa=mesa, usuario=request.user)
            elif datos["accion"] == "finalizar":
                mesa = ServicioRegistroParticipacion.finalizar_escaneo_mesa(
                    mesa=mesa,
                    usuario=request.user,
                    confirmar_sin_inasistencias=datos["confirmar_sin_inasistencias"],
                )
        except ErrorEscaneoMesa as error:
            return _respuesta_error(error)
        return Response({"mesa": ServicioRegistroParticipacion.describir_mesa(mesa)})
