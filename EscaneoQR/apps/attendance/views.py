from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from apps.elections.models import Election

@login_required
def scanner(request, election_id):
    election = get_object_or_404(Election, pk=election_id, is_active=True)
    return render(request, "attendance/scanner.html", {"election": election})
