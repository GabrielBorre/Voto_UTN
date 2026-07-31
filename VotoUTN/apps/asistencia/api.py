from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.elecciones.models import Eleccion
from .serializers import SerializadorCargaManualAsistencia, SerializadorLoteAsistencia
from .services import ServicioAsistencia


class APIVistaAsistenciaLote(APIView):
    def post(self, request, eleccion_id):
        eleccion = get_object_or_404(Eleccion, pk=eleccion_id, is_active=True)

        if "voter_codes" in request.data:
            serializer = SerializadorLoteAsistencia(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = ServicioAsistencia.registrar_lote(
                eleccion=eleccion,
                voter_codes=serializer.validated_data["voter_codes"],
                user=request.user,
            )
            received = len(serializer.validated_data["voter_codes"])
        else:
            serializer = SerializadorCargaManualAsistencia(data=request.data)
            serializer.is_valid(raise_exception=True)
            result = ServicioAsistencia.registrar_manual(
                eleccion=eleccion,
                mesa_numero=serializer.validated_data["mesa_numero"],
                legajo=serializer.validated_data["legajo"],
                user=request.user,
            )
            received = 1

        return Response(
            {
                "registered": result.created,
                "already_registered": result.already_registered,
                "invalid": result.invalid,
                "received": received,
            }
        )
