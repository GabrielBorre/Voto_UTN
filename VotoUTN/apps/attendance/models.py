from django.conf import settings
from django.db import models
from apps.elections.models import Election


class Attendance(models.Model):
    election = models.ForeignKey(Election, on_delete=models.PROTECT, related_name="attendances")
    voter_code = models.CharField(max_length=120)
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("election", "voter_code"), name="unique_attendance_per_election")]
        indexes = [models.Index(fields=("election", "voter_code"))]

    def __str__(self):
        return f"{self.election}: {self.voter_code}"
