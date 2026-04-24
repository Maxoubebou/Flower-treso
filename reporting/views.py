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
    """Page de synthèse TVA (formulaire CA3) avec rafraîchissement automatique."""
    from datetime import date
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

    periode = f"{annee}{mois:02d}"


    # Sauvegarde en session
    request.session['filtre_mois'] = str(mois)
    request.session['filtre_annee'] = str(annee)

    # Récupérer ou créer la déclaration
    decl, created = DeclarationTVA.objects.get_or_create(
        periode=periode,
        defaults={'switch_calcul': 'operation'}
    )

    # Rafraîchissement automatique si non finalisée
    if not decl.finalisee:
        finalise_declaration(decl)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'valider' and not decl.finalisee:
            decl.lien_declaration = request.POST.get('lien_declaration')
            decl.lien_accuse_reception = request.POST.get('lien_accuse_reception')
            decl.lien_ordre_paiement = request.POST.get('lien_ordre_paiement')
            
            # Validation sommaire
            if decl.lien_declaration and decl.lien_accuse_reception:
                # Ordre de paiement obligatoire si reste à payer (L32 > 0)
                if decl.ligne_32 > 0 and not decl.lien_ordre_paiement:
                    messages.error(request, "L'ordre de paiement est obligatoire car vous avez de la TVA à payer.")
                else:
                    decl.finalisee = True
                    decl.date_validation = timezone.now()
                    decl.save()
                    messages.success(request, f"La déclaration de {decl.libelle_periode} a été validée et figée.")
            else:
                messages.error(request, "Veuillez renseigner au moins la déclaration et l'accusé de réception.")
            
            return redirect(request.path + f'?mois={mois}&annee={annee}')

    # Valeurs calculées avec détails pour l'affichage
    computed_data = compute_declaration_tva(periode, decl.switch_calcul)

    # Préparation des lignes pour le template (filtrage des zéros)
    display_lines = []
    # Ordre des lignes à afficher
    order = [
        'ligne_A1', 'ligne_A2', 'ligne_A3', 'ligne_B2', 'ligne_E2',
        'ligne_16', 'ligne_17', 'ligne_20', 'ligne_21', 'ligne_22', 'ligne_23',
        'ligne_25', 'ligne_27', 'ligne_28', 'ligne_32'
    ]
    
    for key in order:
        if key in computed_data:
            line_data = computed_data[key]
        else:
            # Pour les lignes de report/total qui ne sont pas dans compute_declaration_tva
            val = getattr(decl, key, 0)
            line_data = {
                'value': val,
                'details': [],
                'logic': "Valeur calculée ou reportée.",
                'label': decl._meta.get_field(key).help_text
            }
            if key == 'ligne_22':
                line_data['logic'] = "Valeur issue de la précédente déclaration (ou 536€ si Janvier 2026)."

        if line_data['value'] != 0 or key in ['ligne_16', 'ligne_23', 'ligne_32', 'ligne_27']:
            display_lines.append({
                'id': key,
                'label': line_data['label'],
                'value': line_data['value'],
                'details': line_data['details'],
                'logic': line_data['logic']
            })

    MOIS_NOMS = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]

    return render(request, 'reporting/tva_synthese.html', {
        'decl': decl,
        'display_lines': display_lines,
        'meta': computed_data.get('meta', {}),
        'mois': mois,
        'annee': annee,
        'periode': periode,
        'mois_nom': MOIS_NOMS[mois],
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
    total_nb_jeh = bvs.aggregate(total=Sum('nb_jeh'))['total'] or Decimal('0.00')
    base_urssaf_unitaire = p_j.base_urssaf  # On prend celle du profil junior (généralement identique)
    
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
        'total_nb_jeh': total_nb_jeh,
        'base_urssaf_unitaire': base_urssaf_unitaire,
        'lignes': lignes,
        'total_cotisations': total_cotisations,
        'deduction': deduction,
        'montant_a_payer': montant_a_payer,
    })
