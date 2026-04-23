from django.urls import path
from . import views

app_name = 'reporting'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('tva/', views.tva_synthese, name='tva_synthese'),
    path('brc/', views.brc_synthese, name='brc_synthese'),
]
