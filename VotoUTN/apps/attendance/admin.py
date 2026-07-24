from django.contrib import admin
from .models import Attendance

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("voter_code", "election", "scanned_by", "scanned_at")
    list_filter = ("election",)
    search_fields = ("voter_code",)
    readonly_fields = ("scanned_at",)
