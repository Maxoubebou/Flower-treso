from django.contrib import admin
from .models import ImportBatch, Operation


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ('filename', 'nb_rows', 'created_at')
    date_hierarchy = 'created_at'


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'est_credit', 'credit', 'debit', 'date_operation', 'statut', 'import_batch')
    list_filter = ('statut',)
    search_fields = ('libelle', 'reference', 'info_complementaire')
    date_hierarchy = 'date_operation'
    list_editable = ('statut',)
