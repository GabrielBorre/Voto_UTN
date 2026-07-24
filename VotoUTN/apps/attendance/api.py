from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.elections.models import Election
from .serializers import AttendanceBatchSerializer
from .services import AttendanceService


class AttendanceBatchAPIView(APIView):
    def post(self, request, election_id):
        election = get_object_or_404(Election, pk=election_id, is_active=True)
        serializer = AttendanceBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = AttendanceService.register_batch(election=election, voter_codes=serializer.validated_data["voter_codes"], user=request.user)
        return Response({"registered": result.created, "already_registered": result.already_registered, "invalid": result.invalid, "received": len(serializer.validated_data["voter_codes"])})
