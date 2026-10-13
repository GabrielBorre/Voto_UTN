from rest_framework import serializers


class SerializadorLoteAsistencia(serializers.Serializer):
    codigos_qr = serializers.ListField(child=serializers.CharField(max_length=180), allow_empty=False, max_length=30)
    mesa_codigo = serializers.CharField(max_length=40, trim_whitespace=True)


class SerializadorCargaManualAsistencia(serializers.Serializer):
    mesa_codigo = serializers.CharField(max_length=40, trim_whitespace=True)
    dni = serializers.CharField(max_length=12, trim_whitespace=True)


class SerializadorEscaneoMesa(serializers.Serializer):
    accion = serializers.ChoiceField(choices=("consultar", "iniciar", "finalizar"))
    codigo_qr = serializers.CharField(max_length=40, required=False, allow_blank=True)
    codigo_mesa = serializers.CharField(max_length=40, required=False, allow_blank=True)
    confirmar_sin_inasistencias = serializers.BooleanField(required=False, default=False)

    def validate(self, datos):
        if not (datos.get("codigo_qr") or datos.get("codigo_mesa")):
            raise serializers.ValidationError("Indicá el QR o el código de la mesa.")
        return datos
