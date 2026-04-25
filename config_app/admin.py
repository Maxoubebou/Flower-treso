from django.contrib import admin
from .models import LigneBudgetaire, TypeFactureVente, TypeAchat, ParametreTVA, ParametreCotisation, ParametreNDF


@admin.register(LigneBudgetaire)
class LigneBudgetaireAdmin(admin.ModelAdmin):
    list_display = ('nom', 'active', 'ordre')
    list_editable = ('active', 'ordre')


@admin.register(TypeFactureVente)
class TypeFactureVenteAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'suffixe', 'taux_tva_defaut', 'est_cotisation', 'est_subvention', 'active', 'ordre')
    list_editable = ('active', 'ordre')


@admin.register(TypeAchat)
class TypeAchatAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'suffixe', 'active', 'ordre')
    list_editable = ('active', 'ordre')


@admin.register(ParametreTVA)
class ParametreTVAAdmin(admin.ModelAdmin):
    list_display = ('taux', 'libelle', 'actif', 'ordre')
    list_editable = ('actif',)


@admin.register(ParametreCotisation)
class ParametreCotisationAdmin(admin.ModelAdmin):
    list_display = ('type_cotisant', 'base_urssaf', 'assurance_maladie', 'vieillesse_plafonnee')


@admin.register(ParametreNDF)
class ParametreNDFAdmin(admin.ModelAdmin):
    list_display = ('nom', 'montant_ik', 'actif')
    list_editable = ('montant_ik', 'actif')
