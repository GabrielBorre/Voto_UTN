from django.contrib import admin
from django.urls import path
from .views import views

urlpatterns = [
    path('',views.index, name='index'),
    path('justificacion_ausencia',views.justificacion_ausencia,name='justificacion_ausencia'),
    path('preferencia_votacion',views.preferencia_votacion,name='preferencia_votacion'),
    path('preferencia_turno',views.preferencia_turno,name='preferencia_turno'),
    path('inicio/autoridad_de_mesa',views.inicio_autoridad_mesa,name='inicio_autoridad'),
]
#Formato /Rol/nombre_de_pestaña