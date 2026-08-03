from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.elecciones.models import Eleccion
from apps.usuarios.permisos import puede_registrar_participacion
from rest_framework.exceptions import PermissionDenied
from .serializers import SerializadorCargaManualAsistencia, SerializadorLoteAsistencia
from .services import ServicioRegistroParticipacion


class APIVistaAsistenciaLote(APIView):
    def post(self, request, eleccion_id):
        eleccion = get_object_or_404(Eleccion, pk=eleccion_id, habilitada=True)
        if not puede_registrar_participacion(request.user, eleccion):
            raise PermissionDenied("No tenés permisos para registrar participación en esta elección.")

        if "codigos_qr" in request.data:
            serializer = SerializadorLoteAsistencia(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = ServicioRegistroParticipacion.registrar_lote(
                eleccion=eleccion,
                codigos_qr=serializer.validated_data["codigos_qr"],
                usuario=request.user,
            )
            recibidos = len(serializer.validated_data["codigos_qr"])
        else:
            serializer = SerializadorCargaManualAsistencia(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = ServicioRegistroParticipacion.registrar_manual(
                eleccion=eleccion,
                mesa_numero=serializer.validated_data["mesa_numero"],
                dni=serializer.validated_data["dni"],
                usuario=request.user,
            )
            recibidos = 1

        return Response(
            {
                "creados": result.creados,
                "ya_registrados": result.ya_registrados,
                "invalidos": result.invalidos,
                "recibidos": recibidos,
            }
        )
