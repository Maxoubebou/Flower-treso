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

def calculate_cotisations_urssaf(nb_jeh: Decimal) -> dict:
    """
    Calcule systématiquement les cotisations URSSAF pour la Part Junior (JE) 
    et la Part Étudiant (Intervenant).
    """
    from config_app.models import ParametreCotisation

    # Récupération des deux types de paramètres requis
    p_j = ParametreCotisation.objects.get(type_cotisant='junior')
    p_e = ParametreCotisation.objects.get(type_cotisant='etudiant')

    # L'assiette est basée sur la base URSSAF du profil junior
    assiette = (nb_jeh * p_j.base_urssaf).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calc(taux: Decimal) -> Decimal:
        return (assiette * taux / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # --- Calcul Part Junior (JE) ---
    j_maladie = calc(p_j.assurance_maladie)
    j_at = calc(p_j.accident_travail)
    j_vp = calc(p_j.vieillesse_plafonnee)
    j_vd = calc(p_j.vieillesse_deplafonnee)
    j_af = calc(p_j.allocations_familiales)
    j_csgd = calc(p_j.csg_deductible)
    j_csgnd = calc(p_j.csg_non_deductible)
    total_j = j_maladie + j_at + j_vp + j_vd + j_af + j_csgd + j_csgnd

    # --- Calcul Part Étudiant (Intervenant) ---
    e_maladie = calc(p_e.assurance_maladie)
    e_at = calc(p_e.accident_travail)
    e_vp = calc(p_e.vieillesse_plafonnee)
    e_vd = calc(p_e.vieillesse_deplafonnee)
    e_af = calc(p_e.allocations_familiales)
    e_csgd = calc(p_e.csg_deductible)
    e_csgnd = calc(p_e.csg_non_deductible)
    total_e = e_maladie + e_at + e_vp + e_vd + e_af + e_csgd + e_csgnd

    return {
        'assiette': assiette,
        
        # Part Junior
        'j_maladie': j_maladie, 
        'j_at': j_at, 
        'j_vp': j_vp, 
        'j_vd': j_vd,
        'j_af': j_af, 
        'j_csgd': j_csgd, 
        'j_csgnd': j_csgnd, 
        'total_j': total_j,
        
        # Part Étudiant
        'e_maladie': e_maladie, 
        'e_at': e_at, 
        'e_vp': e_vp, 
        'e_vd': e_vd,
        'e_af': e_af, 
        'e_csgd': e_csgd, 
        'e_csgnd': e_csgnd, 
        'total_e': total_e,
        
        'total_global': total_j + total_e
    }
