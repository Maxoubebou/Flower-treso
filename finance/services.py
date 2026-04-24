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
    Nomenclature : FV + AA + MM + NN + _[Type]
    Subvention : S + AA + MM + NN
    """
    from .models import FactureVente

    is_sub = type_facture.est_subvention
    prefix = 'S' if is_sub else 'FV'
    aa = str(annee)[-2:]
    mm = f"{mois:02d}"
    
    # On cherche l'incrément le plus haut pour ce préfixe et ce mois
    base_prefix = f"{prefix}{aa}{mm}"
    existing = FactureVente.objects.filter(numero__startswith=base_prefix).values_list('numero', flat=True)
    
    max_nn = 0
    for num in existing:
        try:
            # Extraction des 2 chiffres après le préfixe temporel
            nn_str = num[len(base_prefix):len(base_prefix)+2]
            nn = int(nn_str)
            if nn > max_nn: max_nn = nn
        except: continue
    
    chrono = max_nn + 1
    nn = f"{chrono:02d}"
    base_ref = f"{prefix}{aa}{mm}{nn}"
    
    if is_sub:
        return base_ref
        
    suffix_map = {'A': '_A', 'S': '_S', 'C': '_C', 'R': '_REF', 'AV': '_AV'}
    ext = suffix_map.get(suffixe, f"_{suffixe}" if suffixe else "")
    return f"{base_ref}{ext}"


def generate_numero_facture_achat(type_achat, annee: int, mois: int) -> str:
    """
    Génère le numéro de facture d'achat.
    Nomenclature : A (fournisseur) ou NF (ndf) + AA + MM + NN (partagé)
    """
    from .models import FactureAchat

    # Même logique : on cherche le chrono le plus élevé (tous préfixes confondus pour les achats)
    aa = str(annee)[-2:]
    mm = f"{mois:02d}"
    
    # On cherche dans les achats commençant par A ou NF pour ce mois
    # Note: comme le chrono est partagé, on regarde les deux préfixes possibles
    # On simplifie en cherchant par date d'opération si le numéro a été sali
    existing = FactureAchat.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois
    ).values_list('numero', flat=True)
    
    max_nn = 0
    for num in existing:
        try:
            # On cherche les 2 chiffres après le préfixe temporel (index 3-5 pour A2404XX ou 4-6 pour NF2404XX)
            p_len = 3 if num.startswith('A') else 4
            nn_str = num[p_len:p_len+2]
            nn = int(nn_str)
            if nn > max_nn: max_nn = nn
        except: continue
        
    chrono = max_nn + 1
    nn = f"{chrono:02d}"
    prefix = 'NF' if type_achat.suffixe == 'NF' else 'A'
    return f"{prefix}{aa}{mm}{nn}"


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
