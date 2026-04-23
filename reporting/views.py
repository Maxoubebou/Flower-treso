from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from .models import DeclarationTVA
from .services import compute_declaration_tva, finalise_declaration
from finance.models import FactureVente, BulletinVersement, FactureAchat
from flower_treso.utils import to_decimal


def dashboard(request):
    """Dashboard principal avec KPIs."""
    from datetime import date
    from django.db.models import Sum, Count

    aujourd_hui = date.today()
    mois_courant = aujourd_hui.month
    annee_courante = aujourd_hui.year

    # KPIs du mois
    ventes_mois = FactureVente.objects.filter(
        date_operation__year=annee_courante,
        date_operation__month=mois_courant
    )
    achats_mois = FactureAchat.objects.filter(
        date_operation__year=annee_courante,
        date_operation__month=mois_courant
    )
    bv_mois = BulletinVersement.objects.filter(
        date_operation__year=annee_courante,
        date_operation__month=mois_courant
    )

    from operations.models import Operation
    ops_pending = Operation.objects.filter(statut='pending').count()

    # Déclaration TVA du mois
    periode = f"{annee_courante}{mois_courant:02d}"
    decl_courante = DeclarationTVA.objects.filter(periode=periode).first()

    # Dernières déclarations
    declarations_recentes = DeclarationTVA.objects.order_by('-periode')[:6]

    ca_mois = sum(v.montant_ttc for v in ventes_mois) or 0
    depenses_mois = sum(a.montant_ttc for a in achats_mois) or 0
    tva_collectee = sum(v.montant_tva for v in ventes_mois) or 0
    tva_deductible = sum(a.montant_tva for a in achats_mois) or 0

    return render(request, 'dashboard.html', {
        'ca_mois': ca_mois,
        'depenses_mois': depenses_mois,
        'tva_collectee': tva_collectee,
        'tva_deductible': tva_deductible,
        'tva_nette': tva_collectee - tva_deductible,
        'nb_ventes': ventes_mois.count(),
        'nb_achats': achats_mois.count(),
        'nb_bv': bv_mois.count(),
        'ops_pending': ops_pending,
        'mois_courant': mois_courant,
        'annee_courante': annee_courante,
        'decl_courante': decl_courante,
        'declarations_recentes': declarations_recentes,
        'aujourd_hui': aujourd_hui,
    })


def tva_synthese(request):
    """Page de synthèse TVA (formulaire CA3)."""
    from datetime import date

    aujourd_hui = date.today()

    # Période sélectionnée
    mois_param = request.GET.get('mois') or request.session.get('filtre_mois')
    # Si c'est une liste (filtre global), on prend le premier élément
    if isinstance(mois_param, list):
        mois_val = mois_param[0] if mois_param else aujourd_hui.month
    else:
        mois_val = mois_param or aujourd_hui.month

    mois = int(mois_val)
    annee_param = request.GET.get('annee') or request.session.get('filtre_annee')
    if isinstance(annee_param, list):
        annee_val = annee_param[0] if annee_param else aujourd_hui.year
    else:
        annee_val = annee_param or aujourd_hui.year
    annee = int(annee_val)    
    periode = f"{annee}{mois:02d}"

    if 'mois' in request.GET:
        request.session['filtre_mois'] = [str(mois)]
    if 'annee' in request.GET:
        request.session['filtre_annee'] = str(annee)

    # Récupérer ou créer la déclaration
    decl, created = DeclarationTVA.objects.get_or_create(
        periode=periode,
        defaults={'switch_calcul': 'operation'}
    )

    if created:
        # Initialisation automatique de la ligne 22 (report mois précédent)
        mois_prec = mois - 1 if mois > 1 else 12
        annee_prec = annee if mois > 1 else annee - 1
        periode_prec = f"{annee_prec}{mois_prec:02d}"
        decl_prec = DeclarationTVA.objects.filter(periode=periode_prec).first()
        if decl_prec:
            decl.ligne_22 = decl_prec.ligne_27
            decl.save()
            finalise_declaration(decl)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'calculer':
            # Recalculer automatiquement
            computed = compute_declaration_tva(periode, decl.switch_calcul)
            for champ, valeur in computed.items():
                setattr(decl, champ, valeur)
            # Ligne 22 : report du mois précédent (auto depuis le mois précédent si pas modifié manuellement)
            if not decl.ligne_22_modifiee_manuellement:
                mois_prec = mois - 1 if mois > 1 else 12
                annee_prec = annee if mois > 1 else annee - 1
                periode_prec = f"{annee_prec}{mois_prec:02d}"
                decl_prec = DeclarationTVA.objects.filter(periode=periode_prec).first()
                decl.ligne_22 = decl_prec.ligne_27 if decl_prec else 0

            finalise_declaration(decl)
            messages.success(request, "Déclaration TVA recalculée.")
            return redirect(request.path + f'?mois={mois}&annee={annee}')

        elif action == 'modifier_ligne_22':
            try:
                decl.ligne_22 = to_decimal(request.POST.get('ligne_22', '0'))
                decl.ligne_22_modifiee_manuellement = True
                decl.save()
                finalise_declaration(decl)
                messages.warning(
                    request,
                    "La ligne 22 (report de crédit) a été modifiée manuellement. "
                    "Vérifiez la cohérence avec la déclaration du mois précédent."
                )
            except Exception as e:
                messages.error(request, f"Erreur : {e}")
            return redirect(request.path + f'?mois={mois}&annee={annee}')

        elif action == 'changer_switch':
            decl.switch_calcul = request.POST.get('switch_calcul', 'operation')
            decl.save()
            messages.info(request, "Switch de calcul mis à jour.")
            return redirect(request.path + f'?mois={mois}&annee={annee}')

    # Valeurs calculées en direct pour l'affichage (sans sauvegarder)
    computed = compute_declaration_tva(periode, decl.switch_calcul)

    # Générer la liste des mois disponibles (12 mois glissants)
    mois_disponibles = []
    for i in range(12):
        m = aujourd_hui.month - i
        a = aujourd_hui.year
        if m <= 0:
            m += 12
            a -= 1
        mois_disponibles.append({'mois': m, 'annee': a, 'periode': f"{a}{m:02d}"})

    MOIS_NOMS = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]

    return render(request, 'reporting/tva_synthese.html', {
        'decl': decl,
        'computed': computed,
        'mois': mois,
        'annee': annee,
        'periode': periode,
        'mois_nom': MOIS_NOMS[mois],
        'mois_disponibles': mois_disponibles,
        'mois_noms': MOIS_NOMS,
    })


def brc_synthese(request):
    """Synthèse BRC (Bordereau Récapitulatif de Cotisations URSSAF)."""
    from datetime import date
    from django.db.models import Sum
    from config_app.models import ParametreCotisation
    from decimal import Decimal

    aujourd_hui = date.today()

    # Période sélectionnée
    mois_param = request.GET.get('mois') or request.session.get('filtre_mois')
    if isinstance(mois_param, list):
        mois = int(mois_param[0]) if mois_param else aujourd_hui.month
    else:
        mois = int(mois_param or aujourd_hui.month)

    annee_param = request.GET.get('annee') or request.session.get('filtre_annee')
    if isinstance(annee_param, list):
        annee = int(annee_param[0]) if annee_param else aujourd_hui.year
    else:
        annee = int(annee_param or aujourd_hui.year)

    # Récupération des bulletins
    bvs = BulletinVersement.objects.filter(
        date_operation__year=annee,
        date_operation__month=mois
    )

    # Calcul des effectifs
    effectif_dernier_jour = 1 if bvs.exists() else 0
    effectif_remunere = bvs.values('intervenant_nom', 'intervenant_prenom').distinct().count() or 0

    # Paramètres de cotisation pour récupérer les taux
    try:
        p_j = ParametreCotisation.objects.get(type_cotisant='junior')
        p_e = ParametreCotisation.objects.get(type_cotisant='etudiant')
    except ParametreCotisation.DoesNotExist:
        messages.error(request, "Paramètres de cotisation manquants. Veuillez les configurer dans les paramètres.")
        return redirect('config:settings_index')

    # Somme des assiettes de tous les bulletins, arrondie à l'entier (le "Salaire arrondi" du BRC)
    total_assiette_brute = bvs.aggregate(total=Sum('assiette'))['total'] or Decimal('0.00')
    total_assiette = total_assiette_brute.quantize(Decimal('1'), rounding='ROUND_HALF_UP')

    # Définition des lignes BRC basées sur la structure URSSAF du projet
    lignes = []
    
    # Mapping des champs du modèle URSSAF aux libellés BRC
    catalogue = [
        {'code': '635D', 'name': 'Assurance Maladie', 'field': 'assurance_maladie'},
        {'code': '100A', 'name': 'Accident du Travail', 'field': 'accident_travail'},
        {'code': '100P', 'name': 'Vieillesse Plafonnée', 'field': 'vieillesse_plafonnee'},
        {'code': '100D', 'name': 'Vieillesse Déplafonnée', 'field': 'vieillesse_deplafonnee'},
        {'code': '430D', 'name': 'Allocations Familiales', 'field': 'allocations_familiales'},
    ]

    for item in catalogue:
        taux_j = getattr(p_j, item['field'])
        taux_e = getattr(p_e, item['field'])
        taux_total = taux_j + taux_e
        # Cotisation = Total Assiette × (Taux Junior + Taux Étudiant) / 100, arrondie à l'entier
        cotisation = (total_assiette * taux_total / Decimal('100')).quantize(Decimal('1'), rounding='ROUND_HALF_UP')
        lignes.append({
            'code': item['code'],
            'name': item['name'],
            'assiette': total_assiette,
            'taux': taux_total,
            'valeur': cotisation
        })

    # Ligne spéciale pour la CSG/CRDS (somme des deux champs deductible et non-deductible)
    taux_csg_j = p_j.csg_deductible + p_j.csg_non_deductible
    taux_csg_e = p_e.csg_deductible + p_e.csg_non_deductible
    taux_csg_total = taux_csg_j + taux_csg_e
    cotisation_csg = (total_assiette * taux_csg_total / Decimal('100')).quantize(Decimal('1'), rounding='ROUND_HALF_UP')
    lignes.append({
        'code': '260D',
        'name': 'CSG / CRDS (Déductible + Non-Déductible)',
        'assiette': total_assiette,
        'taux': taux_csg_total,
        'valeur': cotisation_csg
    })

    # Totaux finaux
    total_cotisations = sum(l['valeur'] for l in lignes)
    deduction = to_decimal(request.GET.get('deduction', '0'))
    montant_a_payer = total_cotisations - deduction

    MOIS_NOMS = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]

    mois_options = [{'id': i, 'nom': MOIS_NOMS[i]} for i in range(1, 13)]

    return render(request, 'reporting/brc_synthese.html', {
        'mois': mois,
        'annee': annee,
        'mois_nom': MOIS_NOMS[mois],
        'mois_options': mois_options,
        'effectif_dernier_jour': effectif_dernier_jour,
        'effectif_remunere': effectif_remunere,
        'lignes': lignes,
        'total_cotisations': total_cotisations,
        'deduction': deduction,
        'montant_a_payer': montant_a_payer,
    })
