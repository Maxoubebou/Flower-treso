from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q

from .models import FactureVente, BulletinVersement, FactureAchat, Etude
from config_app.models import TypeFactureVente, TypeAchat, LigneBudgetaire, ParametreTVA, ParametreCotisation
from flower_treso.utils import to_decimal


def _get_filtres(request):
    # Gestion du mois
    if 'mois' in request.GET:
        mois_raw = request.GET.getlist('mois')
        # Protection contre la sérialisation sauvage de listes dans l'URL
        processed_mois = []
        for m in mois_raw:
            if m.startswith('[') and m.endswith(']'):
                import ast
                try:
                    val = ast.literal_eval(m)
                    if isinstance(val, list):
                        processed_mois.extend([str(item) for item in val])
                except (ValueError, SyntaxError):
                    pass
            elif m:
                processed_mois.append(m)
        
        mois = list(set(processed_mois)) # Déduplication
        request.session['filtre_mois'] = mois
    else:
        mois = request.session.get('filtre_mois') or []

    # Gestion de l'année
    if 'annee' in request.GET:
        annee = request.GET.get('annee')
        request.session['filtre_annee'] = annee
    else:
        annee = request.session.get('filtre_annee')

    return mois, annee


def _appliquer_filtres(qs, mois, annee, champ_date='date_operation'):
    if mois:
        if isinstance(mois, list):
            qs = qs.filter(**{f'{champ_date}__month__in': [int(m) for m in mois]})
        else:
            qs = qs.filter(**{f'{champ_date}__month': int(mois)})
    if annee:
        qs = qs.filter(**{f'{champ_date}__year': int(annee)})
    return qs





# ─── Ventes ──────────────────────────────────────────────────────────────────

def ventes_list(request):
    mois, annee = _get_filtres(request)
    qs = _appliquer_filtres(
        FactureVente.objects.select_related('type_facture', 'etude', 'ligne_budgetaire'),
        mois, annee
    )
    return render(request, 'finance/ventes_list.html', {
        'factures': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
        'total_ht': sum(f.montant_ht for f in qs),
        'total_tva': sum(f.montant_tva for f in qs),
        'total_ttc': sum(f.montant_ttc for f in qs),
    })


def vente_detail(request, pk):
    fv = get_object_or_404(FactureVente, pk=pk)
    return render(request, 'finance/vente_detail.html', {'facture': fv})


def vente_edit(request, pk):
    fv = get_object_or_404(FactureVente, pk=pk)

    if request.method == 'POST':
        try:
            from datetime import datetime
            from finance.services import calculate_tva

            type_facture = TypeFactureVente.objects.get(pk=request.POST['type_facture'])
            taux_tva = to_decimal(request.POST.get('taux_tva', '20'))
            taux_mixte = request.POST.get('taux_mixte') == 'on'

            if taux_mixte:
                montant_ht = abs(to_decimal(request.POST['montant_ht']))
                montant_tva_v = abs(to_decimal(request.POST['montant_tva']))
            else:
                calcul = calculate_tva(fv.montant_ttc, taux_tva)
                montant_ht = abs(calcul['ht'])
                montant_tva_v = abs(calcul['tva'])

            date_envoi_raw = request.POST.get('date_envoi', '')
            date_envoi = datetime.strptime(date_envoi_raw, '%Y-%m-%d').date() if date_envoi_raw else None

            date_op_raw = request.POST.get('date_operation', '')
            if date_op_raw:
                new_date_op = datetime.strptime(date_op_raw, '%Y-%m-%d').date()
                fv.date_operation = new_date_op
                if fv.operation:
                    fv.operation.date_operation = new_date_op
                    fv.operation.save()

            etude_pk = request.POST.get('etude')
            ligne_bud_pk = request.POST.get('ligne_budgetaire')

            fv.type_facture = type_facture
            fv.etude = Etude.objects.get(pk=etude_pk) if etude_pk else None
            fv.libelle = request.POST.get('libelle', fv.libelle)
            fv.lien_drive = request.POST.get('lien_drive', '')
            fv.date_envoi = date_envoi
            fv.taux_tva = taux_tva
            fv.taux_mixte = taux_mixte
            fv.montant_ht = montant_ht
            fv.montant_tva = montant_tva_v
            fv.ligne_budgetaire = LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None
            fv.pays_tva = request.POST.get('pays_tva', 'FR')
            fv.commentaire = request.POST.get('commentaire', '')
            fv.save()

            messages.success(request, f"Facture {fv.numero} mise à jour.")
            return redirect('finance:ventes_list')
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'finance/vente_form.html', {
        'facture': fv,
        'types_facture_vente': TypeFactureVente.objects.filter(active=True),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True),
        'etudes': Etude.objects.filter(active=True).order_by('reference'),
    })


# ─── Bulletins de versement ──────────────────────────────────────────────────

def bv_list(request):
    mois, annee = _get_filtres(request)
    qs = _appliquer_filtres(
        BulletinVersement.objects.select_related('etude'),
        mois, annee
    )
    return render(request, 'finance/bv_list.html', {
        'bulletins': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
    })


def bv_edit(request, pk):
    bv = get_object_or_404(BulletinVersement, pk=pk)

    if request.method == 'POST':
        try:
            from datetime import datetime
            from finance.services import calculate_cotisations_urssaf

            type_cotisant = request.POST.get('type_cotisant', bv.type_cotisant)
            nb_jeh = abs(to_decimal(request.POST.get('nb_jeh', bv.nb_jeh)))
            retrib = abs(to_decimal(request.POST.get('retribution_brute_par_jeh', bv.retribution_brute_par_jeh)))

            params = ParametreCotisation.objects.filter(type_cotisant=type_cotisant).first()
            cotis = calculate_cotisations_urssaf(nb_jeh, type_cotisant, params)

            date_emission_raw = request.POST.get('date_emission', '')
            date_emission = datetime.strptime(date_emission_raw, '%Y-%m-%d').date() if date_emission_raw else None

            date_op_raw = request.POST.get('date_operation', '')
            if date_op_raw:
                new_date_op = datetime.strptime(date_op_raw, '%Y-%m-%d').date()
                bv.date_operation = new_date_op
                if bv.operation:
                    bv.operation.date_operation = new_date_op
                    bv.operation.save()

            etude_pk = request.POST.get('etude')

            bv.etude = Etude.objects.get(pk=etude_pk) if etude_pk else None
            bv.date_emission = date_emission
            bv.intervenant_nom = request.POST.get('intervenant_nom', bv.intervenant_nom)
            bv.intervenant_prenom = request.POST.get('intervenant_prenom', bv.intervenant_prenom)
            bv.nb_jeh = nb_jeh
            bv.retribution_brute_par_jeh = retrib
            bv.taux = request.POST.get('taux', bv.taux)
            bv.type_cotisant = type_cotisant
            bv.assiette = cotis['assiette']
            bv.cotis_assurance_maladie = cotis['assurance_maladie']
            bv.cotis_accident_travail = cotis['accident_travail']
            bv.cotis_vieillesse_plafonnee = cotis['vieillesse_plafonnee']
            bv.cotis_vieillesse_deplafonnee = cotis['vieillesse_deplafonnee']
            bv.cotis_allocations_familiales = cotis['allocations_familiales']
            bv.cotis_csg_deductible = cotis['csg_deductible']
            bv.cotis_csg_non_deductible = cotis['csg_non_deductible']
            bv.total_cotisations_junior = cotis['total_junior']
            bv.total_cotisations_etudiant = cotis['total_etudiant']
            bv.commentaire = request.POST.get('commentaire', bv.commentaire)
            bv.save()

            messages.success(request, f"BV {bv.numero} mis à jour.")
            return redirect('finance:bv_list')
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'finance/bv_form.html', {
        'bv': bv,
        'etudes': Etude.objects.filter(active=True).order_by('reference'),
        'cotisations_params': ParametreCotisation.objects.all(),
    })


# ─── Factures d'achat ────────────────────────────────────────────────────────

def achats_list(request):
    mois, annee = _get_filtres(request)
    qs = _appliquer_filtres(
        FactureAchat.objects.select_related('type_achat', 'ligne_budgetaire'),
        mois, annee
    )
    return render(request, 'finance/achats_list.html', {
        'factures': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
        'total_ht': sum(f.montant_ht for f in qs),
        'total_tva': sum(f.montant_tva for f in qs),
        'total_ttc': sum(f.montant_ttc for f in qs),
    })


def achat_edit(request, pk):
    fa = get_object_or_404(FactureAchat, pk=pk)

    if request.method == 'POST':
        try:
            from datetime import datetime
            from finance.services import calculate_tva

            type_achat = TypeAchat.objects.get(pk=request.POST['type_achat'])
            taux_tva = to_decimal(request.POST.get('taux_tva', '20'))
            taux_compose = request.POST.get('taux_compose') == 'on'

            if taux_compose:
                montant_ht = abs(to_decimal(request.POST['montant_ht']))
                montant_tva_v = abs(to_decimal(request.POST['montant_tva']))
            else:
                calcul = calculate_tva(fa.montant_ttc, taux_tva)
                montant_ht = abs(calcul['ht'])
                montant_tva_v = abs(calcul['tva'])

            date_reception_raw = request.POST.get('date_reception', '')
            date_reception = datetime.strptime(date_reception_raw, '%Y-%m-%d').date() if date_reception_raw else None

            date_op_raw = request.POST.get('date_operation', '')
            if date_op_raw:
                new_date_op = datetime.strptime(date_op_raw, '%Y-%m-%d').date()
                fa.date_operation = new_date_op
                if fa.operation:
                    fa.operation.date_operation = new_date_op
                    fa.operation.save()

            ligne_bud_pk = request.POST.get('ligne_budgetaire')

            fa.type_achat = type_achat
            fa.fournisseur = request.POST.get('fournisseur', fa.fournisseur)
            fa.libelle = request.POST.get('libelle', fa.libelle)
            fa.lien_drive = request.POST.get('lien_drive', '')
            fa.date_reception = date_reception
            fa.categorisation = request.POST.get('categorisation', fa.categorisation)
            fa.taux_tva = taux_tva
            fa.taux_compose = taux_compose
            fa.pays_tva = request.POST.get('pays_tva', fa.pays_tva)
            fa.montant_ht = montant_ht
            fa.montant_tva = montant_tva_v
            fa.ligne_budgetaire = LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None
            fa.commentaire = request.POST.get('commentaire', fa.commentaire)
            fa.save()

            messages.success(request, f"Facture {fa.numero} mise à jour.")
            return redirect('finance:achats_list')
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'finance/achat_form.html', {
        'facture': fa,
        'types_achat': TypeAchat.objects.filter(active=True),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True),
    })


# ─── Études ──────────────────────────────────────────────────────────────────

def etudes_list(request):
    etudes = Etude.objects.all().order_by('reference')
    return render(request, 'finance/etudes_list.html', {'etudes': etudes})


def etude_create(request):
    if request.method == 'POST':
        try:
            Etude.objects.create(
                reference=request.POST['reference'].strip().upper(),
                nom=request.POST['nom'].strip(),
            )
            messages.success(request, "Étude créée avec succès.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
        return redirect('finance:etudes_list')
    return render(request, 'finance/etude_form.html', {})
