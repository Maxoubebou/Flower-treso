from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from .models import DeclarationTVA, DeclarationURSSAF
from .services import compute_declaration_tva, finalise_declaration
from finance.models import FactureVente, BulletinVersement, FactureAchat
from flower_treso.utils import to_decimal


def dashboard(request):
    """Dashboard principal avec KPIs."""
    from datetime import date
    from django.db import models
    from django.db.models import Sum, Count, F
    from finance.models import FactureVente, BulletinVersement, FactureAchat, DemandeNDF
    from operations.models import Operation

    aujourd_hui = date.today()
    mois_courant = aujourd_hui.month
    annee_courante = aujourd_hui.year

    # --- Bloc Personnel pour TOUS ---
    user_ndfs = DemandeNDF.objects.filter(email=request.user.email).order_by('-date_soumission')
    user_ndf_summary = {
        'pending': user_ndfs.filter(statut='pending').count(),
        'waiting': user_ndfs.filter(statut='waiting_payment').count(),
        'completed': user_ndfs.filter(statut='completed').count(),
        'all': user_ndfs[:5] # 5 dernières
    }

    # KPIs globaux (calculés uniquement si l'utilisateur a le droit de les voir sur le dashboard)
    # On récupère les permissions via le context processor (déjà dispo dans le template, mais on peut les utiliser ici aussi)
    from config_app.context_processors import rbac_permissions
    perms = rbac_permissions(request)['user_perms']

    ca_mois = 0
    depenses_mois = 0
    nb_ventes = 0
    nb_achats = 0
    nb_bv = 0
    ops_pending_count = 0
    bv_pending = []
    bv_pending_count = 0
    ndf_pending_count = 0
    ndf_pending_sum = 0
    ndf_waiting_payment_count = 0
    ndf_waiting_payment_sum = 0
    tva_history = []
    urssaf_history = []

    if perms.get('dashboard_show_kpi_global'):
        ventes_mois = FactureVente.objects.filter(date_operation__year=annee_courante, date_operation__month=mois_courant)
        achats_mois = FactureAchat.objects.filter(date_operation__year=annee_courante, date_operation__month=mois_courant)
        bv_mois = BulletinVersement.objects.filter(date_operation__year=annee_courante, date_operation__month=mois_courant)
        
        ca_mois = ventes_mois.aggregate(total=Sum('montant_ttc'))['total'] or 0
        depenses_mois = achats_mois.aggregate(total=Sum('montant_ttc'))['total'] or 0
        nb_ventes = ventes_mois.count()
        nb_achats = achats_mois.count()
        nb_bv = bv_mois.count()
        ops_pending_count = Operation.objects.filter(statut='pending').count()
        bv_pending = BulletinVersement.objects.filter(operation__isnull=True).order_by('-date_emission')[:10]
        bv_pending_count = BulletinVersement.objects.filter(operation__isnull=True).count()

    if perms.get('dashboard_show_kpi_ndf_admin'):
        ndf_pending_count = DemandeNDF.objects.filter(statut='pending').count()
        from finance.models import LigneNDF
        ndf_pending_sum = LigneNDF.objects.filter(demande__statut='pending').aggregate(total=Sum('montant_ttc'))['total'] or 0
        ndf_waiting_payment_count = DemandeNDF.objects.filter(statut='waiting_payment').count()
        ndf_waiting_payment_sum = LigneNDF.objects.filter(demande__statut='waiting_payment').aggregate(total=Sum('montant_ttc'))['total'] or 0

    if perms.get('dashboard_show_tva_urssaf'):
        # --- Gestion URSSAF Dashboard ---
        for i in range(1, 4):
            d = aujourd_hui
            target_month = (d.month - i - 1) % 12 + 1
            target_year = d.year + (d.month - i - 1) // 12
            period_str = f"{target_year}{target_month:02d}"
            deadline_date = date(target_year + (target_month // 12), (target_month % 12) + 1, 15)
            bvs = BulletinVersement.objects.filter(date_envoi__year=target_year, date_envoi__month=target_month)
            participants = bvs.values('intervenant_nom', 'intervenant_prenom').distinct().count()
            total_assiette = bvs.aggregate(total=Sum('assiette'))['total'] or 0
            total_cotis = bvs.aggregate(total=Sum(models.F('total_junior') + models.F('total_etudiant')))['total'] or 0
            decl = DeclarationURSSAF.objects.filter(periode=period_str).first()
            status = 'not_started'
            status_label = "En attente"
            if decl and decl.finalisee:
                status = 'done'; status_label = "BRC déclaré"
            elif aujourd_hui > deadline_date:
                status = 'late'; status_label = f"Retard: {(aujourd_hui - deadline_date).days}j"
            
            months_fr = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
            urssaf_history.append({
                'period': period_str, 'label': f"{months_fr[target_month-1]} {target_year}", 'deadline': deadline_date,
                'decl': decl, 'status': status, 'status_label': status_label,
                'participants': participants, 'assiette': round(total_assiette), 'cotisations': round(total_cotis),
            })

        # --- Gestion TVA Dashboard ---
        for i in range(1, 4):
            d = aujourd_hui
            target_month = (d.month - i - 1) % 12 + 1
            target_year = d.year + (d.month - i - 1) // 12
            period_str = f"{target_year}{target_month:02d}"
            deadline_date = date(target_year + (target_month // 12), (target_month % 12) + 1, 24)
            decl = DeclarationTVA.objects.filter(periode=period_str).first()
            status = 'not_started'; status_label = "En attente"
            if decl and decl.finalisee:
                status = 'done'; status_label = "TVA faite"
            elif aujourd_hui > deadline_date:
                status = 'late'; status_label = f"Retard: {(aujourd_hui - deadline_date).days}j"
            months_fr = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
            tva_history.append({
                'period': period_str, 'label': f"{months_fr[target_month-1]} {target_year}", 'deadline': deadline_date,
                'decl': decl, 'status': status, 'status_label': status_label,
                'amount': decl.ligne_27 if decl and decl.ligne_27 > 0 else (decl.ligne_32 if decl else 0),
                'is_credit': decl and decl.ligne_27 > 0,
            })

    return render(request, 'dashboard.html', {
        'ca_mois': ca_mois,
        'depenses_mois': depenses_mois,
        'nb_ventes': nb_ventes,
        'nb_achats': nb_achats,
        'nb_bv': nb_bv,
        'ops_pending': ops_pending_count,
        'bv_pending': bv_pending,
        'bv_pending_count': bv_pending_count,
        'urssaf_history': urssaf_history,
        'tva_history': tva_history,
        'ndf_pending_count': ndf_pending_count,
        'ndf_pending_sum': ndf_pending_sum,
        'ndf_waiting_payment_count': ndf_waiting_payment_count,
        'ndf_waiting_payment_sum': ndf_waiting_payment_sum,
        'user_ndf': user_ndf_summary,
        'aujourd_hui': aujourd_hui,
    })


def tva_synthese(request):
    """Page de synthèse TVA (formulaire CA3) avec verrouillage séquentiel."""
    from datetime import date
    aujourd_hui = date.today()

    # Logique de période forcée : on commence en Janvier 2026
    # On cherche la dernière déclaration validée
    derniere_validee = DeclarationTVA.objects.filter(finalisee=True).order_by('-periode').first()
    
    if not derniere_validee:
        # Si aucune n'est validée, on commence en Janvier 2026
        annee = 2026
        mois = 1
    else:
        # On passe au mois suivant la dernière validée
        an_v = int(derniere_validee.periode[:4])
        mo_v = int(derniere_validee.periode[4:])
        if mo_v == 12:
            annee = an_v + 1
            mois = 1
        else:
            annee = an_v
            mois = mo_v + 1
            
    periode = f"{annee}{mois:02d}"

    # Sauvegarde en session (pour info)
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
        'ligne_08', 'ligne_16', 'ligne_17', 'ligne_20', 'ligne_21', 'ligne_22', 'ligne_23',
        'ligne_TD'
    ]


    
    for key in order:
        if key == 'ligne_TD':
            val_16 = getattr(decl, 'ligne_16', 0)
            val_23 = getattr(decl, 'ligne_23', 0)
            line_data = {
                'value': val_16 - val_23,
                'details': [],
                'logic': "Calcul : Total TVA brute due (16) - Total TVA à déduire (23).",
                'label': "TVA due"
            }
        elif key in computed_data:
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


        if line_data.get('value') != 0 or key in ['ligne_16', 'ligne_23', 'ligne_TD']:

            display_lines.append({
                'id': key,
                'label': line_data['label'],
                'value': line_data['value'],
                'extra_value': line_data.get('extra_value'), # Added this
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




def urssaf_save_link(request):
    """Enregistre le lien de preuve pour une déclaration URSSAF."""
    if request.method == 'POST':
        periode = request.POST.get('periode')
        lien = request.POST.get('lien_preuve')
        
        if periode and lien:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Saving URSSAF link: {periode} -> {lien}")
            decl, created = DeclarationURSSAF.objects.get_or_create(periode=periode)
            decl.lien_preuve = lien
            decl.finalisee = True
            decl.date_declaration = timezone.now()
            decl.save()
            messages.success(request, f"Preuve de déclaration enregistrée pour {decl.libelle_periode}.")
        else:
            print(f"DEBUG: missing data: periode={periode}, lien={lien}")
        
    if request.headers.get('HX-Request'):
        from django.http import HttpResponse
        response = HttpResponse()
        response['HX-Refresh'] = 'true'
        return response

    return redirect('reporting:dashboard')
