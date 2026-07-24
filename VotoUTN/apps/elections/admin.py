from django.contrib import admin
from .models import Election, Voter

@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_at", "ends_at", "is_active")
    list_filter = ("is_active",)


@admin.register(Voter)
class VoterAdmin(admin.ModelAdmin):
    list_display = ("id", "legajo", "name", "dni")
    search_fields = ("legajo", "name", "dni")
    ordering = ("legajo",)
