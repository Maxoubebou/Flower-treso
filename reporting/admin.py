from django.contrib import admin
from .models import DeclarationTVA


@admin.register(DeclarationTVA)
class DeclarationTVAAdmin(admin.ModelAdmin):
    list_display = ('periode', 'libelle_periode', 'switch_calcul', 'ligne_16', 'ligne_23', 'ligne_28', 'ligne_27', 'finalisee', 'updated_at')
    list_filter = ('switch_calcul', 'finalisee')
    search_fields = ('periode',)
    readonly_fields = ('created_at', 'updated_at')
