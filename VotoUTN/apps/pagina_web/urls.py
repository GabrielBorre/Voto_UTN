from django.contrib import admin
from django.urls import path
from .views import *
urlpatterns = [
    path('',index, name='index'),
    path('justificacion_ausencia',justificacion_ausencia,name='justificacion_ausencia'),
    path('preferencia_votacion',preferencia_votacion,name='preferencia_votacion'),
    path('preferencia_turno',preferencia_turno,name='preferencia_turno'),
    path('inicio/autoridad_de_mesa',inicio_autoridad_mesa,name='inicio_autoridad'),
]