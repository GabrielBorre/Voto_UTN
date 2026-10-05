from django.db.models import Q
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.elecciones.models import Eleccion
from apps.mesas.models import AsignacionMesa
from .models import RegistroPadron


class SerializadorConsultaPadron(serializers.Serializer):
    codigo = serializers.CharField(max_length=20, allow_blank=False, trim_whitespace=True)


class APIVistaConsultaPadron(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SerializadorConsultaPadron(data=request.data)
        serializer.is_valid(raise_exception=True)
        codigo = serializer.validated_data["codigo"]

        registro = (
            RegistroPadron.objects.filter(
                activo=True,
                eleccion__habilitada=True,
                eleccion__estado=Eleccion.Estado.ABIERTA,
            )
            .filter(Q(elector__dni=codigo) | Q(elector__legajo=codigo))
            .select_related(
                "elector",
                "sede",
                "eleccion_claustro_departamento__departamento",
                "eleccion_claustro_departamento__eleccion_claustro__claustro",
                "asignacion_mesa__mesa",
            )
            .order_by("-eleccion__fecha_inicio")
            .first()
        )
        if registro is None:
            return Response(
                {"detail": "No se encontró un padrón activo para ese DNI o legajo."},
                status=404,
            )

        try:
            numero_mesa = registro.asignacion_mesa.mesa.numero
            mesa = f"Mesa {numero_mesa}"
        except AsignacionMesa.DoesNotExist:
            mesa = "Sin asignar"

        return Response(
            {
                "claustro": registro.eleccion_claustro_departamento.eleccion_claustro.claustro.nombre,
                "nombre": registro.elector.nombre,
                "apellido": registro.elector.apellido,
                "dni": registro.elector.dni,
                "sede": registro.sede.nombre if registro.sede else "No informada",
                "especialidad": registro.eleccion_claustro_departamento.departamento.nombre,
                "mesa": mesa,
            }
        )