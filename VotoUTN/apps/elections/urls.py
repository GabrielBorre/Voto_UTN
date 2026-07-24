from django.urls import path
from .views import election_list

urlpatterns = [path("", election_list, name="election-list")]
