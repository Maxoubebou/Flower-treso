"""
reporting/services.py
Logique de calcul simplifiée et robuste pour la déclaration TVA (CA3).

================================================================================
GUIDE DE MODIFICATION / AJOUT DE LIGNES TVA
================================================================================
Pour ajouter une nouvelle ligne à la synthèse :
1. Modèle (models.py) : Ajouter un DecimalField 'ligne_XXX'.
2. Services (compute_declaration_tva) :
    a. Définir un QuerySet filtré pour les factures concernées.
    b. Calculer la valeur avec _round2(sum(...)).
    c. Ajouter une entrée dans le dictionnaire 'results' :
       results['ligne_XXX'] = {
           'value': ...,
           'details': get_details(votre_qs, 'vente'|'achat'),
           'logic': "Texte explicatif pour l'utilisateur",
           'label': "Libellé de la ligne"
       }
3. Services (finalise_declaration) : La ligne sera automatiquement reportée sur le modèle
   grâce à la boucle sur 'computed.items()'.
4. Views (tva_synthese) : Ajouter 'ligne_XXX' dans la liste 'order' pour définir sa position.
================================================================================
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from django.db.models import Sum, Q

from finance.models import FactureVente, FactureAchat
from .models import DeclarationTVA

def _round0(value) -> Decimal:
    """Arrondi à l'unité la plus proche pour la synthèse."""
    if value is None:
        return Decimal('0')
    return Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)

def compute_declaration_tva(periode: str, switch: str = 'operation') -> dict:
    """
    Calcule les lignes de la déclaration TVA avec le détail des factures associées.
    L'affichage principal utilise des arrondis à l'unité.
    """
    annee = int(periode[:4])
    mois = int(periode[4:])

    # --- Initialisation des données sources ---
    ventes_qs = FactureVente.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois,
    ).select_related('type_facture')

    achats_qs = FactureAchat.objects.filter(
        date_reception__year=annee,
        date_reception__month=mois,
    )

    achats_manquants = FactureAchat.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois,
        date_reception__isnull=True
    ).exclude(taux_tva=0)

    # --- Définition des filtres ---
    v_imposables_qs = ventes_qs.exclude(
        type_facture__est_cotisation=True
    ).exclude(pays_tva='extracom').exclude(montant_tva=0)
    
    v_cotisations_qs = ventes_qs.filter(type_facture__est_cotisation=True)
    a_intracom_qs = achats_qs.filter(pays_tva='intracom')
    v_20_qs = v_imposables_qs.filter(taux_tva=20)

    def get_details(qs):
        return [{
            'id': obj.id,
            'date': obj.date_operation,
            'tiers': getattr(obj, 'tiers', getattr(obj, 'fournisseur', '')),
            'libelle': obj.libelle,
            'ht': obj.montant_ht,
            'tva': obj.montant_tva,
            'ttc': obj.montant_ttc
        } for obj in qs]

    results = {}

    # Ligne A1
    a1_val = sum(v.montant_ht for v in v_imposables_qs)
    results['ligne_A1'] = {
        'value': _round0(a1_val),
        'details': get_details(v_imposables_qs),
        'logic': "Somme des montants Hors Taxe (HT) des ventes (avec TVA > 0) imposables.",
        'label': "Ventes et prestations de services HT"
    }

    # Ligne 08
    l08_base = sum(v.montant_ht for v in v_20_qs)
    l08_taxe = sum(v.montant_tva for v in v_20_qs)
    results['ligne_08'] = {
        'value': _round0(l08_base),
        'extra_value': _round0(l08_taxe),
        'details': get_details(v_20_qs),
        'logic': "Taux normal 20% : Base HT et Taxe due.",
        'label': "08 — Taux normal 20%"
    }
    results['ligne_08_base'] = {'value': _round0(l08_base), 'hidden': True}
    results['ligne_08_taxe'] = {'value': _round0(l08_taxe), 'hidden': True}

    # Autres lignes (Vides pour l'instant)
    for l in ['ligne_A2', 'ligne_A3', 'ligne_B2', 'ligne_E2', 'ligne_17', 'ligne_21']:
        results[l] = {
            'value': Decimal('0'),
            'details': [],
            'logic': "Calcul non automatisé.",
            'label': DeclarationTVA._meta.get_field(l).help_text
        }
    
    # Ligne 16
    l16_val = l08_taxe # On pourrait sommer d'autres taux si besoin
    results['ligne_16'] = {
        'value': _round0(l16_val),
        'details': get_details(v_20_qs),
        'logic': "Total de la TVA brute due.",
        'label': "16 — Total TVA brute due"
    }

    # Ligne 20
    l20_val = sum(a.montant_tva for a in achats_qs)
    results['ligne_20'] = {
        'value': _round0(l20_val),
        'details': get_details(achats_qs),
        'logic': "Somme de la TVA déductible sur achats.",
        'label': "20 — Autres biens et services (TVA déductible)"
    }

    # Metadonnées
    results['meta'] = {
        'achats_manquants': get_details(achats_manquants),
        'achats_manquants_count': achats_manquants.count()
    }

    return results

def get_report_tva(periode: str) -> Decimal:
    """Détermine le montant du report de crédit (Ligne 22)."""
    annee = int(periode[:4])
    mois = int(periode[4:])
    if annee == 2026 and mois == 1:
        return Decimal('536')
    
    mois_prec = mois - 1
    annee_prec = annee
    if mois_prec == 0:
        mois_prec = 12
        annee_prec = annee - 1
    periode_prec = f"{annee_prec}{mois_prec:02d}"
    
    decl_prec = DeclarationTVA.objects.filter(periode=periode_prec).first()
    if decl_prec:
        return _round0(decl_prec.ligne_27)
    return Decimal('0')

def finalise_declaration(declaration: DeclarationTVA):
    """
    Calcule et sauvegarde les totaux de la déclaration.
    Utilise les valeurs arrondies à l'unité pour les calculs de cascade.
    """
    computed = compute_declaration_tva(declaration.periode, declaration.switch_calcul)
    
    # 1. Mise à jour des lignes de base à partir des arrondis
    for key, data in computed.items():
        if hasattr(declaration, key):
            setattr(declaration, key, data['value'])

    # 2. Gestion du report (Ligne 22)
    declaration.ligne_22 = get_report_tva(declaration.periode)

    # 3. Calcul des totaux en cascade avec des arrondis à l'unité
    # Ligne 23 : Total TVA déductible = L20 + L21 + L22
    declaration.ligne_23 = _round0(declaration.ligne_20) + _round0(declaration.ligne_21) + _round0(declaration.ligne_22)

    # Ligne 25 : Total TVA Brute = L16 + L17 + ...
    declaration.ligne_25 = _round0(declaration.ligne_16) + _round0(declaration.ligne_17)

    # Calcul du solde
    if declaration.ligne_23 > declaration.ligne_25:
        # Crédit de TVA (Ligne 27)
        declaration.ligne_27 = declaration.ligne_23 - declaration.ligne_25
        declaration.ligne_28 = Decimal('0')
    else:
        # TVA à payer (Ligne 28)
        declaration.ligne_28 = declaration.ligne_25 - declaration.ligne_23
        declaration.ligne_27 = Decimal('0')

    # Ligne 32 : Total à payer
    declaration.ligne_32 = declaration.ligne_28

    declaration.save()
