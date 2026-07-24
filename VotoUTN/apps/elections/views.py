from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Election

@login_required
def election_list(request):
    return render(request, "elections/list.html", {"elections": Election.objects.filter(is_active=True)})
