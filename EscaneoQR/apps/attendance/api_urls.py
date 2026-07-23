from django.urls import path
from .api import AttendanceBatchAPIView

urlpatterns = [path("elections/<int:election_id>/attendance/", AttendanceBatchAPIView.as_view(), name="attendance-batch-api")]
