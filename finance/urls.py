from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Ventes
    path('ventes/', views.ventes_list, name='ventes_list'),
    path('ventes/<int:pk>/', views.vente_detail, name='vente_detail'),
    path('ventes/<int:pk>/edit/', views.vente_edit, name='vente_edit'),
    # Bulletins de versement
    path('bv/', views.bv_list, name='bv_list'),
    path('bv/<int:pk>/edit/', views.bv_edit, name='bv_edit'),
    # Achats
    path('achats/', views.achats_list, name='achats_list'),
    path('achats/<int:pk>/edit/', views.achat_edit, name='achat_edit'),
    # Études
    path('etudes/', views.etudes_list, name='etudes_list'),
    path('etudes/nouvelle/', views.etude_create, name='etude_create'),
    # Utils
    path('quick-assign-budget/', views.set_budget_line, name='set_budget_line'),
    path('quick-update-drive/', views.set_drive_link, name='set_drive_link'),
    path('quick-update-cat/', views.set_categorisation, name='set_categorisation'),
]
