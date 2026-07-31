from rest_framework import serializers


class SerializadorLoteAsistencia(serializers.Serializer):
    voter_codes = serializers.ListField(child=serializers.CharField(max_length=180), allow_empty=False, max_length=30)


class SerializadorCargaManualAsistencia(serializers.Serializer):
    mesa_numero = serializers.IntegerField(min_value=1)
    legajo = serializers.CharField(max_length=20, trim_whitespace=True)
