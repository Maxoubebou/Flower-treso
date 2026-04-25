from django.contrib import admin
from .models import Etude, FactureVente, BulletinVersement, FactureAchat, DemandeNDF, LigneNDF


@admin.register(Etude)
class EtudeAdmin(admin.ModelAdmin):
    list_display = ('reference', 'nom', 'active', 'created_at')
    list_filter = ('active',)
    search_fields = ('reference', 'nom')


@admin.register(FactureVente)
class FactureVenteAdmin(admin.ModelAdmin):
    list_display = ('numero', 'type_facture', 'etude', 'libelle', 'date_operation', 'taux_tva', 'montant_ttc', 'pays_tva')
    list_filter = ('type_facture', 'pays_tva', 'taux_tva')
    search_fields = ('numero', 'libelle')
    date_hierarchy = 'date_operation'
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BulletinVersement)
class BulletinVersementAdmin(admin.ModelAdmin):
    list_display = ('numero', 'intervenant_prenom', 'intervenant_nom', 'etude', 'nb_jeh', 'date_operation')
    search_fields = ('numero', 'intervenant_nom', 'intervenant_prenom')
    date_hierarchy = 'date_operation'
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FactureAchat)
class FactureAchatAdmin(admin.ModelAdmin):
    list_display = ('numero', 'type_achat', 'fournisseur', 'date_operation', 'taux_tva', 'montant_ttc', 'categorisation', 'immobilisation', 'rib_beneficiaire')
    list_filter = ('type_achat', 'pays_tva', 'categorisation', 'immobilisation')
    search_fields = ('numero', 'fournisseur', 'libelle')
    date_hierarchy = 'date_operation'
    readonly_fields = ('created_at', 'updated_at', 'immobilisation')


class LigneNDFInline(admin.TabularInline):
    model = LigneNDF
    extra = 0


@admin.register(DemandeNDF)
class DemandeNDFAdmin(admin.ModelAdmin):
    list_display = ('id', 'nom_beneficiaire', 'email', 'date_soumission', 'statut')
    list_filter = ('statut', 'date_soumission')
    search_fields = ('nom_beneficiaire', 'email')
    inlines = [LigneNDFInline]
