from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.elecciones.models import Eleccion
from .serializers import SerializadorLoteAsistencia
from .services import ServicioAsistencia


class APIVistaAsistenciaLote(APIView):
    def post(self, request, eleccion_id):
        eleccion = get_object_or_404(Eleccion, pk=eleccion_id, is_active=True)
        serializer = SerializadorLoteAsistencia(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ServicioAsistencia.registrar_lote(eleccion=eleccion, voter_codes=serializer.validated_data["voter_codes"], user=request.user)
        return Response({"registered": result.created, "already_registered": result.already_registered, "invalid": result.invalid, "received": len(serializer.validated_data["voter_codes"])})
