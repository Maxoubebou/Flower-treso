"""
finance/services.py
Logique métier : nomenclatures automatiques, calculs TVA, cotisations URSSAF.
"""
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from config_app.models import ParametreCotisation


# ─── Numérotation automatique ────────────────────────────────────────────────

def generate_numero_facture_vente(type_facture, annee: int, mois: int, suffixe: str = '') -> str:
    """
    Génère le numéro de facture de vente.
    Format : FV[AAAA][MM][NNN][suffixe] ou S[AAAA][MM][NNN] pour subventions.
    """
    from .models import FactureVente

    prefix = 'S' if type_facture.est_subvention else 'FV'
    count = FactureVente.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois,
        numero__startswith=prefix,
    ).count()
    chrono = count + 1
    return f"{prefix}{annee}{mois:02d}{chrono:03d}{suffixe}"


def generate_numero_facture_achat(type_achat, annee: int, mois: int) -> str:
    """
    Génère le numéro de facture d'achat.
    Format : FA_[AAAA][MM][NNN][F|NF]
    """
    from .models import FactureAchat

    suffixe = type_achat.suffixe  # 'F' ou 'NF'
    count = FactureAchat.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois,
    ).count()
    chrono = count + 1
    return f"FA_{annee}{mois:02d}{chrono:03d}{suffixe}"


def generate_numero_bv(annee: int) -> str:
    """
    Génère le numéro de BV.
    Format : BV_[AAAA]-[NNN], incrémental sur l'année.
    Unicité garantie.
    """
    from .models import BulletinVersement

    # Trouver le plus grand index existant de l'année
    existing = BulletinVersement.objects.filter(
        numero__startswith=f"BV_{annee}-"
    ).order_by('-numero')

    if existing.exists():
        last_num = existing.first().numero
        try:
            last_idx = int(last_num.split('-')[-1])
        except (ValueError, IndexError):
            last_idx = 0
        new_idx = last_idx + 1
    else:
        new_idx = 1

    return f"BV_{annee}-{new_idx:03d}"


# ─── Calculs TVA ─────────────────────────────────────────────────────────────

def calculate_tva(montant_ttc: Decimal, taux: Decimal) -> dict:
    """
    Calcule HT et TVA à partir du TTC et du taux.

    Returns:
        {'ht': Decimal, 'tva': Decimal}
    """
    taux_decimal = taux / Decimal('100')
    ht = (montant_ttc / (1 + taux_decimal)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    tva = (montant_ttc - ht).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {'ht': ht, 'tva': tva}


def get_taux_tva_defaut(type_facture) -> Decimal:
    """Retourne le taux de TVA par défaut selon le type de facture."""
    return Decimal(str(type_facture.taux_tva_defaut))


# ─── Calculs cotisations URSSAF ──────────────────────────────────────────────

def calculate_cotisations_urssaf(
    nb_jeh: Decimal,
    type_cotisant: str,
    params: ParametreCotisation | None = None,
) -> dict:
    """
    Calcule les cotisations URSSAF pour un BV.

    Args:
        nb_jeh: Nombre de jours-équivalents-hommes
        type_cotisant: 'junior' ou 'etudiant'
        params: Instance ParametreCotisation (chargée depuis la DB si non fournie)

    Returns:
        dict avec toutes les cotisations détaillées + totaux
    """
    if params is None:
        params = ParametreCotisation.objects.get(type_cotisant=type_cotisant)

    assiette = (nb_jeh * params.base_urssaf).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def cotis(taux_pct: Decimal) -> Decimal:
        return (assiette * taux_pct / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    assurance_maladie = cotis(params.assurance_maladie)
    accident_travail = cotis(params.accident_travail)
    vieillesse_plafonnee = cotis(params.vieillesse_plafonnee)
    vieillesse_deplafonnee = cotis(params.vieillesse_deplafonnee)
    allocations_familiales = cotis(params.allocations_familiales)
    csg_deductible = cotis(params.csg_deductible)
    csg_non_deductible = cotis(params.csg_non_deductible)

    # Répartition junior vs étudiant
    if type_cotisant == 'junior':
        total_junior = (assurance_maladie + accident_travail + vieillesse_plafonnee
                        + vieillesse_deplafonnee + allocations_familiales)
        total_etudiant = Decimal('0')
    else:
        total_junior = Decimal('0')
        total_etudiant = (vieillesse_plafonnee + vieillesse_deplafonnee
                          + csg_deductible + csg_non_deductible)

    total_cotisations = total_junior + total_etudiant

    return {
        'assiette': assiette,
        'assurance_maladie': assurance_maladie,
        'accident_travail': accident_travail,
        'vieillesse_plafonnee': vieillesse_plafonnee,
        'vieillesse_deplafonnee': vieillesse_deplafonnee,
        'allocations_familiales': allocations_familiales,
        'csg_deductible': csg_deductible,
        'csg_non_deductible': csg_non_deductible,
        'total_junior': total_junior,
        'total_etudiant': total_etudiant,
        'total_cotisations': total_cotisations,
        'params': params,
    }
