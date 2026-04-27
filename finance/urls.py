from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Ventes
    path('ventes/', views.ventes_list, name='ventes_list'),
    path('ventes/export/', views.vente_export_csv, name='vente_export_csv'),
    path('update-field/', views.update_invoice_field, name='update_invoice_field'),
    path('set-taux-tva/', views.set_taux_tva, name='set_taux_tva'),
    path('refresh-invoice-cell/', views.refresh_invoice_cell, name='refresh_invoice_cell'),
    path('ventes/<int:pk>/', views.vente_detail, name='vente_detail'),
    path('ventes/<int:pk>/edit/', views.vente_edit, name='vente_edit'),
    # Bulletins de versement
    path('bv/', views.bv_list, name='bv_list'),
    path('bv/generation/', views.bv_generation, name='bv_generation'),
    path('bv/<int:pk>/edit/', views.bv_edit, name='bv_edit'),
    path('bv/<int:pk>/delete/', views.bv_delete, name='bv_delete'),
    path('bv/<int:pk>/pdf/', views.bv_pdf_export, name='bv_pdf_export'),
    path('bv/<int:pk>/unlink/', views.bv_unlink_operation, name='bv_unlink_operation'),
    path('bv/update-field/', views.update_bv_field, name='update_bv_field'),



    # Achats
    path('achats/', views.achats_list, name='achats_list'),
    path('achats/export/', views.achat_export_csv, name='achat_export_csv'),
    path('achats/<int:pk>/edit/', views.achat_edit, name='achat_edit'),
    path('achats/<int:pk>/delete/', views.achat_delete, name='achat_delete'),
    # Notes de Frais
    path('ndf/demander/', views.ndf_submit, name='ndf_submit'),
    path('ndf/demander/<int:pk>/', views.ndf_submit, name='ndf_edit'),
    path('ndf/gerer/', views.ndf_manage, name='ndf_manage'),
    path('ndf/historique/', views.ndf_history, name='ndf_history'),
    path('ndf/<int:pk>/valider/', views.ndf_validate, name='ndf_validate'),
    path('ndf/<int:pk>/rejeter/', views.ndf_reject, name='ndf_reject'),
    path('ndf/<int:pk>/precisions/', views.ndf_request_info, name='ndf_request_info'),
    path('ndf/<int:pk>/pdf/', views.ndf_download_pdf, name='ndf_download_pdf'),
    path('ndf/<int:pk>/supprimer/', views.ndf_delete, name='ndf_delete'),
    # Études
    path('etudes/', views.etudes_list, name='etudes_list'),
    path('etudes/nouvelle/', views.etude_create, name='etude_create'),
    # Utils
    path('quick-assign-budget/', views.set_budget_line, name='set_budget_line'),
    path('quick-update-drive/', views.set_drive_link, name='set_drive_link'),
    path('quick-update-cat/', views.set_categorisation, name='set_categorisation'),
    path('set-type-achat/', views.set_type_achat, name='set_type_achat'),
    path('set-type-vente/', views.set_type_vente, name='set_type_vente'),
    path('set-etude/', views.set_etude, name='set_etude'),
    path('operations-ignorees/', views.ignored_operations_list, name='ignored_operations_list'),
    path('operations-ignorees/reset/<int:pk>/', views.operation_reset, name='operation_reset'),
    path('check-reference/', views.check_reference_exists, name='check_reference_exists'),
]
