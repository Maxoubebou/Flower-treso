from django.urls import path
from . import views

app_name = 'config'

urlpatterns = [
    path('', views.settings_index, name='settings_index'),
    path('tva/<int:pk>/update/', views.taux_tva_update, name='taux_tva_update'),
    path('tva/create/', views.taux_tva_create, name='taux_tva_create'),
    path('cotisations/update-unified/', views.cotisation_unified_update, name='cotisation_unified_update'),
    path('budget/create/', views.ligne_budgetaire_create, name='ligne_budgetaire_create'),
    path('budget/<int:pk>/toggle/', views.ligne_budgetaire_toggle, name='ligne_budgetaire_toggle'),
    path('type-vente/create/', views.type_facture_vente_create, name='type_facture_vente_create'),
    path('type-achat/create/', views.type_achat_create, name='type_achat_create'),
    path('autofill-rules/create/', views.autofill_rule_create, name='autofill_rule_create'),
    path('autofill-rules/<int:pk>/delete/', views.autofill_rule_delete, name='autofill_rule_delete'),
]
