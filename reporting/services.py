"""
reporting/services.py
Logique de calcul de la déclaration TVA (formulaire CA3).
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from finance.models import FactureVente, FactureAchat


def _round2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def compute_declaration_tva(periode: str, switch: str = 'operation') -> dict:
    """
    Calcule toutes les lignes du formulaire CA3 pour une période AAAAMM.

    Args:
        periode: Chaîne 'AAAAMM'
        switch: 'operation' (date bancaire) ou 'facture' (date d'envoi/réception)

    Returns:
        dict de toutes les lignes du formulaire
    """
    annee = int(periode[:4])
    mois = int(periode[4:])

    # ─── Filtrer les factures de vente ───────────────────────────────────────
    if switch == 'facture':
        ventes_qs = FactureVente.objects.filter(
            date_envoi__year=annee,
            date_envoi__month=mois,
        )
    else:
        ventes_qs = FactureVente.objects.filter(
            date_operation__year=annee,
            date_operation__month=mois,
        )

    # ─── Filtrer les factures d'achat ────────────────────────────────────────
    if switch == 'facture':
        achats_qs = FactureAchat.objects.filter(
            date_reception__year=annee,
            date_reception__month=mois,
        )
    else:
        achats_qs = FactureAchat.objects.filter(
            date_operation__year=annee,
            date_operation__month=mois,
        )

    # ─── A1 : Ventes imposables HT (hors cotisations et subventions hors UE) ─
    ventes_imposables = ventes_qs.exclude(
        type_facture__est_cotisation=True
    ).exclude(pays_tva='extracom')

    ligne_A1 = _round2(abs(sum(v.montant_ht for v in ventes_imposables if v.montant_ht)))

    # ─── E2 : Opérations non imposables = cotisations ────────────────────────
    ventes_cotisation = ventes_qs.filter(type_facture__est_cotisation=True)
    ligne_E2 = _round2(abs(sum(v.montant_ht for v in ventes_cotisation if v.montant_ht)))

    # ─── E1 : Exportations extra-UE ──────────────────────────────────────────
    ventes_extra = ventes_qs.filter(pays_tva='extracom')
    ligne_E1 = _round2(abs(sum(v.montant_ht for v in ventes_extra if v.montant_ht)))

    # ─── B2 : Acquisitions intracommunautaires (achats intracom biens) ────────
    achats_intracom = achats_qs.filter(pays_tva='intracom')
    ligne_B2 = _round2(abs(sum(a.montant_ht for a in achats_intracom if a.montant_ht)))

    # ─── Ligne 08 : TVA 20% ──────────────────────────────────────────────────
    ventes_20 = ventes_imposables.filter(taux_tva=20, pays_tva='FR')
    ligne_08_base = _round2(abs(sum(v.montant_ht for v in ventes_20 if v.montant_ht)))
    ligne_08_taxe = _round2(ligne_08_base * Decimal('0.20'))

    # Lignes 09 / 09b (taux réduits) — valeur 0 par défaut (pas de ventes à taux réduit)
    ventes_10 = ventes_imposables.filter(taux_tva=10, pays_tva='FR')
    ligne_09_base = _round2(abs(sum(v.montant_ht for v in ventes_10 if v.montant_ht)))
    ligne_09_taxe = _round2(ligne_09_base * Decimal('0.10'))

    ventes_55 = ventes_imposables.filter(taux_tva__in=[Decimal('5.5'), Decimal('5.50')], pays_tva='FR')
    ligne_09b_base = _round2(abs(sum(v.montant_ht for v in ventes_55 if v.montant_ht)))
    ligne_09b_taxe = _round2(ligne_09b_base * Decimal('0.055'))

    # ─── Ligne 16 : Total TVA brute ──────────────────────────────────────────
    ligne_16 = _round2(ligne_08_taxe + ligne_09_taxe + ligne_09b_taxe)

    # ─── Ligne 17 : TVA sur acquisitions intracom ────────────────────────────
    ligne_17 = _round2(ligne_B2 * Decimal('0.20'))

    # ─── Ligne 20 : TVA déductible sur achats ────────────────────────────────
    ligne_20 = _round2(abs(sum(a.montant_tva for a in achats_qs if a.montant_tva)))

    return {
        # Section A
        'ligne_A1': ligne_A1,
        'ligne_A2': Decimal('0'),
        'ligne_A3': Decimal('0'),
        'ligne_A4': Decimal('0'),
        'ligne_A5': Decimal('0'),
        # Section B
        'ligne_B1': Decimal('0'),
        'ligne_B2': ligne_B2,
        'ligne_B3': Decimal('0'),
        'ligne_B4': Decimal('0'),
        'ligne_B5': Decimal('0'),
        # Section E
        'ligne_E1': ligne_E1,
        'ligne_E2': ligne_E2,
        # TVA brute
        'ligne_08_base': ligne_08_base,
        'ligne_08_taxe': ligne_08_taxe,
        'ligne_09_base': ligne_09_base,
        'ligne_09_taxe': ligne_09_taxe,
        'ligne_09b_base': ligne_09b_base,
        'ligne_09b_taxe': ligne_09b_taxe,
        'ligne_16': ligne_16,
        'ligne_17': ligne_17,
        # TVA déductible
        'ligne_20': ligne_20,
        'ligne_21': Decimal('0'),
        # ligne_22 et ligne_23 à compléter avec le report et les valeurs manuelles
    }


def finalise_declaration(declaration) -> None:
    """
    Calcule et enregistre toutes les lignes calculées d'une DeclarationTVA.
    Les lignes 20-22 doivent déjà être renseignées si modifiées manuellement.
    """
    computed = compute_declaration_tva(declaration.periode, declaration.switch_calcul)

    # Appliquer les valeurs calculées (sans écraser la ligne 22 si saisie manuellement)
    for champ, valeur in computed.items():
        setattr(declaration, champ, valeur)

    # Ligne 23 = 20 + 21 + 22
    declaration.ligne_23 = _round2(
        declaration.ligne_20 + declaration.ligne_21 + declaration.ligne_22
    )

    # Crédits ou taxe à payer
    solde = declaration.ligne_23 - declaration.ligne_16
    if solde > 0:
        declaration.ligne_25 = solde
        declaration.ligne_27 = solde
        declaration.ligne_28 = Decimal('0')
        declaration.ligne_32 = Decimal('0')
    else:
        declaration.ligne_25 = Decimal('0')
        declaration.ligne_27 = Decimal('0')
        declaration.ligne_28 = _round2(abs(solde))
        declaration.ligne_32 = declaration.ligne_28

    declaration.save()
