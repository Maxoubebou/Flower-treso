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

def _round2(value) -> Decimal:
    if value is None:
        return Decimal('0.00')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def compute_declaration_tva(periode: str, switch: str = 'operation') -> dict:
    """
    Calcule les lignes de la déclaration TVA avec le détail des factures associées.
    """
    annee = int(periode[:4])
    mois = int(periode[4:])

    # --- Initialisation des données sources ---
    # Ventes : Filtrées par date d'opération bancaire (encaissement)
    ventes_qs = FactureVente.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois,
    ).select_related('type_facture')

    # Achats : Filtrés par date de réception de facture (déclaration sur les débits/réceptions)
    # Note : Le switch pourrait permettre de changer, mais on reste sur le standard métier habituel
    achats_qs = FactureAchat.objects.filter(
        date_reception__year=annee,
        date_reception__month=mois,
    )

    # Détecter les achats sans date de réception (TVA non encore déductible)
    achats_manquants = FactureAchat.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois,
        date_reception__isnull=True
    ).exclude(taux_tva=0)

    # --- Définition des filtres pour les lignes ---
    
    # A1 : Ventes imposables (hors cotisations et hors exportations extra-UE)
    # AJOUT : Uniquement ventes avec TVA non nulle
    v_imposables_qs = ventes_qs.exclude(
        type_facture__est_cotisation=True
    ).exclude(pays_tva='extracom').exclude(montant_tva=0)
    
    # E2 : Cotisations
    v_cotisations_qs = ventes_qs.filter(type_facture__est_cotisation=True)
    
    # B2 : Acquisitions intracommunautaires (Achats UE)
    a_intracom_qs = achats_qs.filter(pays_tva='intracom')

    # 08 : Taux normal 20%
    v_20_qs = v_imposables_qs.filter(taux_tva=20)

    # --- Calcul des lignes et récupération des détails ---

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
    a1_val = _round2(sum(v.montant_ht for v in v_imposables_qs))
    results['ligne_A1'] = {
        'value': a1_val,
        'details': get_details(v_imposables_qs),
        'logic': "Somme des montants Hors Taxe (HT) des ventes (avec TVA > 0) imposables en France ou en UE.",
        'label': "Ventes et prestations de services HT"
    }

    # Ligne 08
    l08_base = _round2(sum(v.montant_ht for v in v_20_qs))
    l08_taxe = _round2(sum(v.montant_tva for v in v_20_qs))
    results['ligne_08'] = {
        'value': l08_base, # Montant principal affiché
        'extra_value': l08_taxe, # Deuxième valeur demandée
        'details': get_details(v_20_qs),
        'logic': "Taux normal 20% : Affiche la Base HT (gauche) et la Taxe due (droite).",
        'label': "08 — Taux normal 20%"
    }
    # Ces champs sont aussi persistés
    results['ligne_08_base'] = {'value': l08_base, 'hidden': True}
    results['ligne_08_taxe'] = {'value': l08_taxe, 'hidden': True}

    # Ligne A2 (Autres - 0 pour l'instant)

    results['ligne_A2'] = {
        'value': Decimal('0.00'),
        'details': [],
        'logic': "Calcul non automatisé pour l'instant.",
        'label': "Autres opérations imposables"
    }

    # Ligne A3 (Importations - 0 pour l'instant)
    results['ligne_A3'] = {
        'value': Decimal('0.00'),
        'details': [],
        'logic': "Calcul non automatisé pour l'instant.",
        'label': "Importations"
    }

    # Ligne B2
    b2_val = _round2(sum(a.montant_ht for a in a_intracom_qs))
    results['ligne_B2'] = {
        'value': b2_val,
        'details': get_details(a_intracom_qs),
        'logic': "Somme des montants Hors Taxe (HT) des achats réalisés auprès de fournisseurs situés dans l'UE.",
        'label': "Acquisitions intracommunautaires HT"
    }

    # Ligne E2
    e2_val = _round2(sum(v.montant_ht for v in v_cotisations_qs))
    results['ligne_E2'] = {
        'value': e2_val,
        'details': get_details(v_cotisations_qs),
        'logic': "Somme des montants Hors Taxe (HT) des factures de type 'Cotisation'.",
        'label': "Autres opérations non imposables (Cotisations)"
    }

    # Ligne 16 : TVA brute due (sur ventes imposables)
    l16_val = _round2(sum(v.montant_tva for v in v_imposables_qs))
    results['ligne_16'] = {
        'value': l16_val,
        'details': get_details(v_imposables_qs),
        'logic': "Somme de la TVA collectée sur les ventes imposables.",
        'label': "Total TVA brute due"
    }

    # Ligne 17 : TVA sur acquisitions intracom
    l17_val = _round2(b2_val * Decimal('0.20'))
    results['ligne_17'] = {
        'value': l17_val,
        'details': results['ligne_B2']['details'],
        'logic': "Auto-liquidation : 20% du montant HT de la ligne B2.",
        'label': "Dont TVA sur acquisitions intracommunautaires"
    }

    # Ligne 20 : TVA déductible sur achats
    l20_val = _round2(sum(a.montant_tva for a in achats_qs))
    results['ligne_20'] = {
        'value': l20_val,
        'details': get_details(achats_qs),
        'logic': "Somme de la TVA déductible sur toutes les factures d'achat reçues sur la période.",
        'label': "Autres biens et services (TVA déductible)"
    }

    # Ligne 21 : Autre TVA à déduire
    results['ligne_21'] = {
        'value': Decimal('0.00'),
        'details': [],
        'logic': "Calcul non automatisé.",
        'label': "Autre TVA à déduire"
    }

    # Metadonnées additionnelles pour le dashboard
    results['meta'] = {
        'achats_manquants': get_details(achats_manquants),
        'achats_manquants_count': achats_manquants.count()
    }


    return results

def get_report_tva(periode: str) -> Decimal:
    """
    Détermine le montant du report de crédit (Ligne 22).
    Règle spécifiée par l'utilisateur :
    - Janvier 2026 : fixé à 536 €
    - Autres cas : ligne 27 du mois précédent.
    """
    annee = int(periode[:4])
    mois = int(periode[4:])

    if annee == 2026 and mois == 1:
        return Decimal('536.00')

    # Calcul du mois précédent
    mois_prec = mois - 1
    annee_prec = annee
    if mois_prec == 0:
        mois_prec = 12
        annee_prec = annee - 1
    
    periode_prec = f"{annee_prec}{mois_prec:02d}"
    
    from .models import DeclarationTVA
    decl_prec = DeclarationTVA.objects.filter(periode=periode_prec).first()
    if decl_prec:
        return decl_prec.ligne_27
    
    return Decimal('0.00')

def finalise_declaration(declaration) -> None:
    """
    Calcule et enregistre toutes les lignes de la déclaration.
    """
    computed = compute_declaration_tva(declaration.periode, declaration.switch_calcul)

    # Mise à jour des champs du modèle à partir des valeurs calculées
    for key, data in computed.items():
        if key != 'meta' and hasattr(declaration, key):
            setattr(declaration, key, data['value'])

    # Gestion du report (Ligne 22)
    declaration.ligne_22 = get_report_tva(declaration.periode)

    # Ligne 23 : Total TVA déductible (20+21+22)
    declaration.ligne_23 = _round2(
        declaration.ligne_20 + declaration.ligne_21 + declaration.ligne_22
    )

    # Calcul du solde
    solde = declaration.ligne_23 - declaration.ligne_16
    
    if solde > 0:
        # Crédit de TVA
        declaration.ligne_25 = _round2(solde)
        declaration.ligne_27 = _round2(solde)
        declaration.ligne_28 = Decimal('0.00')
        declaration.ligne_32 = Decimal('0.00')
    else:
        # TVA due
        declaration.ligne_25 = Decimal('0.00')
        declaration.ligne_27 = Decimal('0.00')
        declaration.ligne_28 = _round2(abs(solde))
        declaration.ligne_32 = declaration.ligne_28

    declaration.save()
