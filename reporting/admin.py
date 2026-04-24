from django.contrib import admin
from .models import DeclarationTVA


@admin.register(DeclarationTVA)
class DeclarationTVAAdmin(admin.ModelAdmin):
    list_display = ('periode', 'libelle_periode', 'ligne_16', 'ligne_23', 'ligne_28', 'ligne_32', 'ligne_27', 'finalisee', 'date_validation')
    list_filter = ('finalisee',)
    search_fields = ('periode',)
    readonly_fields = ('created_at', 'updated_at', 'date_validation')
    fieldsets = (
        ('Période', {
            'fields': ('periode', 'finalisee', 'date_validation')
        }),
        ('Opérations (HT)', {
            'fields': ('ligne_A1', 'ligne_A2', 'ligne_A3', 'ligne_B2', 'ligne_E2')
        }),
        ('TVA Brute', {
            'fields': ('ligne_16', 'ligne_17')
        }),
        ('TVA Déductible', {
            'fields': ('ligne_20', 'ligne_21', 'ligne_22', 'ligne_23')
        }),
        ('Résultat', {
            'fields': ('ligne_25', 'ligne_27', 'ligne_28', 'ligne_32')
        }),
        ('Validation', {
            'fields': ('lien_declaration', 'lien_accuse_reception', 'lien_ordre_paiement')
        }),
        ('Système', {
            'fields': ('created_at', 'updated_at')
        }),
    )

