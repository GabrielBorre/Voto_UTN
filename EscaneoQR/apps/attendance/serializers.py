from rest_framework import serializers

class AttendanceBatchSerializer(serializers.Serializer):
    voter_codes = serializers.ListField(child=serializers.CharField(max_length=120), allow_empty=False, max_length=30)
