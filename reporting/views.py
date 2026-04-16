from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from .models import DeclarationTVA
from .services import compute_declaration_tva, finalise_declaration
from finance.models import FactureVente, BulletinVersement, FactureAchat


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
    mois = int(request.GET.get('mois') or request.session.get('filtre_mois') or aujourd_hui.month)
    annee = int(request.GET.get('annee') or request.session.get('filtre_annee') or aujourd_hui.year)
    periode = f"{annee}{mois:02d}"

    if request.GET.get('mois'):
        request.session['filtre_mois'] = str(mois)
    if request.GET.get('annee'):
        request.session['filtre_annee'] = str(annee)

    # Récupérer ou créer la déclaration
    decl, created = DeclarationTVA.objects.get_or_create(
        periode=periode,
        defaults={'switch_calcul': 'operation'}
    )

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
                from decimal import Decimal
                decl.ligne_22 = Decimal(request.POST.get('ligne_22', '0'))
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
