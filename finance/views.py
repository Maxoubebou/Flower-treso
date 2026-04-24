from django.shortcuts import render, redirect, get_object_or_404
import csv
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token

from .models import FactureVente, BulletinVersement, FactureAchat, Etude
from .services import generate_numero_bv
from operations.models import Operation

from config_app.models import TypeFactureVente, TypeAchat, LigneBudgetaire, ParametreTVA, ParametreCotisation
from flower_treso.utils import to_decimal
from django.db import IntegrityError


def _get_filtres(request):
    # Gestion du mois
    if 'mois' in request.GET:
        mois_raw = request.GET.getlist('mois')
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
        mois = list(set(processed_mois))
        request.session['filtre_mois'] = mois
    else:
        mois = request.session.get('filtre_mois') or []

    # Gestion de l'année (multi-sélection)
    if 'annee' in request.GET:
        annee_raw = request.GET.getlist('annee')
        annee = [a for a in annee_raw if a]
        request.session['filtre_annee'] = annee
    else:
        annee = request.session.get('filtre_annee', ['2025'])
        if isinstance(annee, str):
            annee = [annee] if annee else []

    return mois, annee


def _appliquer_filtres(qs, mois, annee, champ_date='date_operation', fallback_champ_date=None):
    from django.db.models.functions import Coalesce

    if fallback_champ_date and champ_date != fallback_champ_date:
        qs = qs.annotate(effective_filter_date=Coalesce(champ_date, fallback_champ_date))
        filter_date_field = 'effective_filter_date'
    else:
        filter_date_field = champ_date

    if mois:
        if isinstance(mois, list):
            qs = qs.filter(**{f'{filter_date_field}__month__in': [int(m) for m in mois]})
        else:
            qs = qs.filter(**{f'{filter_date_field}__month': int(mois)})
    if annee:
        if isinstance(annee, list) and len(annee) > 0:
            qs = qs.filter(**{f'{filter_date_field}__year__in': [int(a) for a in annee]})
        elif isinstance(annee, str) and annee:
            qs = qs.filter(**{f'{filter_date_field}__year': int(annee)})
    return qs



def _ordonner_qs(qs, request, allowed_fields):
    """Helper pour trier les querysets selon les paramètres GET."""
    sort_by = request.GET.get('sort', None)
    order = request.GET.get('order', 'asc')
    
    if sort_by in allowed_fields:
        if order == 'desc':
            qs = qs.order_by(f'-{sort_by}')
        else:
            qs = qs.order_by(sort_by)
    return qs


# ─── Ventes ──────────────────────────────────────────────────────────────────

def ventes_list(request):
    mois, annee = _get_filtres(request)
    date_filter_type = request.session.get('date_filter_type', 'operation')
    champ_date = 'date_envoi' if date_filter_type == 'facture' else 'date_operation'

    qs = _appliquer_filtres(
        FactureVente.objects.select_related('type_facture', 'etude', 'ligne_budgetaire'),
        mois, annee,
        champ_date=champ_date,
        fallback_champ_date='date_operation' if date_filter_type == 'facture' else None
    )
    # Sorting
    allowed_fields = ['date_operation', 'taux_tva', 'montant_ht', 'montant_tva', 'montant_ttc']
    qs = _ordonner_qs(qs, request, allowed_fields)

    # Filtrage des lignes budgétaires : uniquement celles présentes dans le budget actif
    all_budget_lines = LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct()

    return render(request, 'finance/ventes_list.html', {
        'factures': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
        'total_ht': sum(f.montant_ht for f in qs),
        'total_tva': sum(f.montant_tva for f in qs),
        'total_ttc': sum(f.montant_ttc for f in qs),
        'all_budget_lines': all_budget_lines,
        'all_types_vente': TypeFactureVente.objects.filter(active=True),
        'current_sort': request.GET.get('sort'),
        'current_order': request.GET.get('order', 'asc'),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True).order_by('ordre'),
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
            fv.tiers = request.POST.get('tiers', '')
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

    from finance.models import Etude as EtudeModel
    return render(request, 'finance/vente_form.html', {
        'facture': fv,
        'types_facture_vente': TypeFactureVente.objects.filter(active=True),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True),
        'etudes': EtudeModel.objects.filter(active=True).order_by('reference'),
        'historique_tiers': FactureVente.objects.exclude(tiers="").values_list('tiers', flat=True).distinct()[:50],
    })


# ─── Bulletins de versement ──────────────────────────────────────────────────

def bv_list(request):
    mois, annee = _get_filtres(request)
    qs = _appliquer_filtres(
        BulletinVersement.objects.select_related('etude', 'ligne_budgetaire'),
        mois, annee
    )
    # Sorting
    allowed_fields = ['date_operation', 'nb_jeh', 'assiette', 'total_cotisations_junior', 'total_cotisations_etudiant']
    qs = _ordonner_qs(qs, request, allowed_fields)

    return render(request, 'finance/bv_list.html', {
        'bulletins': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
        'all_budget_lines': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'all_etudes': Etude.objects.filter(active=True).order_by('reference'),
        'current_sort': request.GET.get('sort'),
        'current_order': request.GET.get('order', 'asc'),
    })


def bv_edit(request, pk):
    bv = get_object_or_404(BulletinVersement, pk=pk)

    if request.method == 'POST':
        try:
            from datetime import datetime
            from finance.services import calculate_cotisations_urssaf

            nb_jeh = abs(to_decimal(request.POST.get('nb_jeh', str(bv.nb_jeh))))
            retrib = abs(to_decimal(request.POST.get('retribution_brute_par_jeh', str(bv.retribution_brute_par_jeh))))
            
            # Recalcul des cotisations basé sur nb_jeh
            cotis = calculate_cotisations_urssaf(nb_jeh)

            # Dates
            date_emission_raw = request.POST.get('date_emission', '')
            bv.date_emission = datetime.strptime(date_emission_raw, '%Y-%m-%d').date() if date_emission_raw else None

            date_op_raw = request.POST.get('date_operation', '')
            if date_op_raw:
                new_date_op = datetime.strptime(date_op_raw, '%Y-%m-%d').date()
                bv.date_operation = new_date_op
                if bv.operation:
                    bv.operation.date_operation = new_date_op
                    bv.operation.save()

            etude_pk = request.POST.get('etude')
            ligne_bud_pk = request.POST.get('ligne_budgetaire')

            bv.etude = Etude.objects.get(pk=etude_pk) if etude_pk else None
            bv.ligne_budgetaire = LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None
            
            # Informations Intervenant
            bv.intervenant_nom = request.POST.get('intervenant_nom', bv.intervenant_nom)
            bv.intervenant_prenom = request.POST.get('intervenant_prenom', bv.intervenant_prenom)
            bv.adresse = request.POST.get('adresse', bv.adresse)
            bv.code_postal = request.POST.get('code_postal', bv.code_postal)
            bv.ville = request.POST.get('ville', bv.ville)
            bv.num_secu = request.POST.get('num_secu', bv.num_secu)
            bv.nom_mission = request.POST.get('nom_mission', bv.nom_mission)
            bv.ref_rm = request.POST.get('ref_rm', bv.ref_rm)
            bv.ref_avrm = request.POST.get('ref_avrm', bv.ref_avrm)

            bv.nb_jeh = nb_jeh
            bv.retribution_brute_par_jeh = retrib
            bv.assiette = cotis['assiette']

            # Part Junior
            bv.j_assurance_maladie = cotis['j_maladie']
            bv.j_accident_travail = cotis['j_at']
            bv.j_vieillesse_plafonnee = cotis['j_vp']
            bv.j_vieillesse_deplafonnee = cotis['j_vd']
            bv.j_allocations_familiales = cotis['j_af']
            bv.j_csg_deductible = cotis['j_csgd']
            bv.j_csg_non_deductible = cotis['j_csgnd']
            bv.total_junior = cotis['total_j']

            # Part Étudiant
            bv.e_assurance_maladie = cotis['e_maladie']
            bv.e_accident_travail = cotis['e_at']
            bv.e_vieillesse_plafonnee = cotis['e_vp']
            bv.e_vieillesse_deplafonnee = cotis['e_vd']
            bv.e_allocations_familiales = cotis['e_af']
            bv.e_csg_deductible = cotis['e_csgd']
            bv.e_csg_non_deductible = cotis['e_csgnd']
            bv.total_etudiant = cotis['total_e']

            bv.total_global = cotis['total_global']
            bv.commentaire = request.POST.get('commentaire', bv.commentaire)
            bv.lien_drive = request.POST.get('lien_drive', bv.lien_drive)
            
            bv.save()

            messages.success(request, f"BV {bv.numero} mis à jour.")
            return redirect('finance:bv_list')
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, 'finance/bv_form.html', {
        'bv': bv,
        'etudes': Etude.objects.filter(active=True).order_by('reference'),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'param_j': ParametreCotisation.objects.filter(type_cotisant='junior').first(),
        'param_e': ParametreCotisation.objects.filter(type_cotisant='etudiant').first(),
    })


# ─── Factures d'achat ────────────────────────────────────────────────────────

def achats_list(request):
    mois, annee = _get_filtres(request)
    date_filter_type = request.session.get('date_filter_type', 'operation')
    champ_date = 'date_reception' if date_filter_type == 'facture' else 'date_operation'

    qs = _appliquer_filtres(
        FactureAchat.objects.select_related('type_achat', 'ligne_budgetaire'),
        mois, annee,
        champ_date=champ_date,
        fallback_champ_date='date_operation' if date_filter_type == 'facture' else None
    )
    # Sorting
    allowed_fields = ['date_operation', 'taux_tva', 'montant_ht', 'montant_tva', 'montant_ttc']
    qs = _ordonner_qs(qs, request, allowed_fields)

    return render(request, 'finance/achats_list.html', {
        'factures': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
        'total_ht': sum(f.montant_ht for f in qs),
        'total_tva': sum(f.montant_tva for f in qs),
        'total_ttc': sum(f.montant_ttc for f in qs),
        'all_budget_lines': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'all_types_achat': TypeAchat.objects.filter(active=True),
        'current_sort': request.GET.get('sort'),
        'current_order': request.GET.get('order', 'asc'),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True).order_by('ordre'),
    })


def achat_edit(request, pk):
    fa = get_object_or_404(FactureAchat, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action', 'edit')

        if action == 'convert_to_bv':
            # Conversion FA → BV : supprimer FA, créer BV lié à la même opération
            try:
                from datetime import datetime
                from finance.services import generate_numero_bv, calculate_cotisations_urssaf

                nb_jeh = abs(to_decimal(request.POST.get('nb_jeh', '0')))
                retrib = abs(to_decimal(request.POST.get('retribution_brute_par_jeh', '0')))
                cotis = calculate_cotisations_urssaf(nb_jeh)

                numero_propose = request.POST.get('numero') or generate_numero_bv(fa.date_operation.year)
                if BulletinVersement.objects.filter(numero=numero_propose).exists():
                    messages.error(request, f"Le numéro BV {numero_propose} existe déjà.")
                    return redirect('finance:achat_edit', pk=pk)

                date_emission_raw = request.POST.get('date_emission', '')
                date_emission = datetime.strptime(date_emission_raw, '%Y-%m-%d').date() if date_emission_raw else None
                etude_pk = request.POST.get('etude')
                ligne_bud_pk = request.POST.get('ligne_budgetaire')

                operation = fa.operation  # Garder la référence avant suppression
                date_op = fa.date_operation

                bv = BulletinVersement.objects.create(
                    operation=operation,
                    numero=numero_propose,
                    etude=Etude.objects.get(pk=etude_pk) if etude_pk else None,
                    ligne_budgetaire=LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None,
                    date_operation=date_op,
                    date_emission=date_emission,
                    reference_virement=getattr(operation, 'reference', '') or '',
                    intervenant_nom=request.POST.get('intervenant_nom', ''),
                    intervenant_prenom=request.POST.get('intervenant_prenom', ''),
                    adresse=request.POST.get('adresse', ''),
                    code_postal=request.POST.get('code_postal', ''),
                    ville=request.POST.get('ville', ''),
                    num_secu=request.POST.get('num_secu', ''),
                    nom_mission=request.POST.get('nom_mission', ''),
                    ref_rm=request.POST.get('ref_rm', ''),
                    ref_avrm=request.POST.get('ref_avrm', ''),
                    nb_jeh=nb_jeh,
                    retribution_brute_par_jeh=retrib,
                    assiette=cotis['assiette'],
                    j_assurance_maladie=cotis['j_maladie'],
                    j_accident_travail=cotis['j_at'],
                    j_vieillesse_plafonnee=cotis['j_vp'],
                    j_vieillesse_deplafonnee=cotis['j_vd'],
                    j_allocations_familiales=cotis['j_af'],
                    j_csg_deductible=cotis['j_csgd'],
                    j_csg_non_deductible=cotis['j_csgnd'],
                    total_junior=cotis['total_j'],
                    e_assurance_maladie=cotis['e_maladie'],
                    e_accident_travail=cotis['e_at'],
                    e_vieillesse_plafonnee=cotis['e_vp'],
                    e_vieillesse_deplafonnee=cotis['e_vd'],
                    e_allocations_familiales=cotis['e_af'],
                    e_csg_deductible=cotis['e_csgd'],
                    e_csg_non_deductible=cotis['e_csgnd'],
                    total_etudiant=cotis['total_e'],
                    total_global=cotis['total_global'],
                    commentaire=request.POST.get('commentaire', ''),
                )

                # Détacher l'opération de la FA avant suppression pour éviter la cascade
                fa.operation = None
                fa.save()
                fa.delete()

                messages.success(request, f"FA convertie en BV {bv.numero} avec succès.")
                return redirect('finance:bv_list')
            except Exception as e:
                messages.error(request, f"Erreur lors de la conversion en BV : {e}")
                return redirect('finance:achat_edit', pk=pk)

        # Action edit classique
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

    from finance.models import Etude as EtudeModel
    return render(request, 'finance/achat_form.html', {
        'facture': fa,
        'types_achat': TypeAchat.objects.filter(active=True),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True),
        'etudes': EtudeModel.objects.filter(active=True).order_by('reference'),
        'cotisations_params': ParametreCotisation.objects.all(),
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

@require_POST
def set_budget_line(request):
    """Endpoint HTMX pour changer la ligne budgétaire d'un objet."""
    obj_type = request.POST.get('type')
    obj_id = request.POST.get('id')
    lb_id = request.POST.get('lb_id')
    lb_name = request.POST.get('lb_name')
    
    lb = None
    # 1. Tentative par ID
    if lb_id and lb_id.isdigit():
        lb = LigneBudgetaire.objects.filter(pk=lb_id).first()
    
    # 2. Fallback par Nom (plus robuste pour les entrées manuelles)
    if not lb and lb_name:
        lb = LigneBudgetaire.objects.filter(nom__iexact=lb_name.strip()).first()
    
    if obj_type == 'vente':
        obj = get_object_or_404(FactureVente, pk=obj_id)
    elif obj_type == 'achat':
        obj = get_object_or_404(FactureAchat, pk=obj_id)
    elif obj_type == 'bv':
        obj = get_object_or_404(BulletinVersement, pk=obj_id)
    else:
        return HttpResponse("Type inconnu", status=400)
    
    obj.ligne_budgetaire = lb
    obj.save()
    
    response = HttpResponse(lb.nom if lb else "—")
    response['HX-Trigger'] = 'budgetLineSaved'
    return response


@require_POST
def set_drive_link(request):
    """Endpoint HTMX pour mettre à jour le lien Drive."""
    obj_type = request.POST.get('type')
    obj_id = request.POST.get('id')
    url = request.POST.get('url', '').strip()

    if obj_type == 'vente':
        obj = get_object_or_404(FactureVente, pk=obj_id)
    elif obj_type == 'achat':
        obj = get_object_or_404(FactureAchat, pk=obj_id)
    elif obj_type == 'bv':
        obj = get_object_or_404(BulletinVersement, pk=obj_id)
    else:
        return HttpResponse("Type inconnu", status=400)

    obj.lien_drive = url
    obj.save()
    response = HttpResponse(url)
    response['HX-Trigger'] = 'driveLinkSaved'
    return response


@require_POST
def set_categorisation(request):
    from django.middleware.csrf import get_token
    obj_id = request.POST.get('id')
    new_cat = request.POST.get('categorisation')
    fa = get_object_or_404(FactureAchat, pk=obj_id)

    if new_cat in ('service', 'bien', 'immobilisation'):
        if new_cat == 'immobilisation':
            fa.immobilisation = True
            fa.categorisation = 'immobilisation'
        else:
            fa.immobilisation = False
            fa.categorisation = new_cat
        fa.save()

    # Configuration des couleurs pastel / transparentes
    if fa.immobilisation:
        bg, border, text = 'rgba(168, 85, 247, 0.15)', '#a855f7', '#7e22ce'
    elif fa.categorisation == 'bien':
        bg, border, text = 'rgba(59, 130, 246, 0.15)', '#3b82f6', '#1d4ed8'
    else:
        bg, border, text = 'rgba(34, 197, 94, 0.15)', '#22c55e', '#15803d'

    csrf_token = get_token(request)
    
    html = f"""
    <select name="categorisation"
            class="badge-select"
            style="font-size: .7rem; padding: 2px 12px; border-radius: 12px; cursor: pointer; font-weight: 700; appearance: none; -webkit-appearance: none; text-align: center; transition: all 0.2s; border: 1px solid {border}; color: {text}; background-color: {bg};"
            hx-post="/finance/set-categorisation/"
            hx-vals='{{"id": "{fa.id}"}}'
            hx-headers='{{"X-CSRFToken": "{csrf_token}"}}'
            hx-swap="outerHTML"
            onchange="const colors = {{
                'service': {{bg: 'rgba(34, 197, 94, 0.15)', border: '#22c55e', text: '#15803d'}},
                'bien': {{bg: 'rgba(59, 130, 246, 0.15)', border: '#3b82f6', text: '#1d4ed8'}},
                'immobilisation': {{bg: 'rgba(168, 85, 247, 0.15)', border: '#a855f7', text: '#7e22ce'}}
            }};
            const c = colors[this.value];
            this.style.backgroundColor = c.bg;
            this.style.borderColor = c.border;
            this.style.color = c.text;">
      <option value="service" style="background-color: white; color: #333;" {"selected" if fa.categorisation == 'service' and not fa.immobilisation else ""}>Service</option>
      <option value="bien" style="background-color: white; color: #333;" {"selected" if fa.categorisation == 'bien' and not fa.immobilisation else ""}>Bien</option>
      <option value="immobilisation" style="background-color: white; color: #333;" {"selected" if fa.immobilisation else ""}>Immobilisation</option>
    </select>
    """
    return HttpResponse(html)

@require_POST
def set_type_achat(request):
    """Endpoint HTMX pour changer le type d'achat inline."""
    obj_id = request.POST.get('id')
    type_id = request.POST.get('type_achat')
    fa = get_object_or_404(FactureAchat, pk=obj_id)
    
    if type_id:
        new_type = get_object_or_404(TypeAchat, pk=type_id)
        fa.type_achat = new_type
        fa.save()

    # Logique de couleur : Bleu pour Fournisseur, Orange pour Note de frais
    is_ndf = "frais" in fa.type_achat.nom.lower()
    bg, border, text = ('rgba(245, 158, 11, 0.15)', '#f59e0b', '#b45309') if is_ndf else ('rgba(6, 182, 212, 0.15)', '#06b6d4', '#0e7490')

    csrf_token = get_token(request)
    all_types = TypeAchat.objects.filter(active=True)
    
    options = "".join([
        f'<option value="{t.id}" style="background-color: white; color: #333;" {"selected" if fa.type_achat_id == t.id else ""}>{t.nom}</option>'
        for t in all_types
    ])

    html = f"""
    <select name="type_achat"
            style="font-size: .7rem; padding: 2px 12px; border-radius: 12px; cursor: pointer; font-weight: 700; appearance: none; -webkit-appearance: none; text-align: center; transition: all 0.2s; border: 1px solid {border}; color: {text}; background-color: {bg};"
            hx-post="/finance/set-type-achat/"
            hx-vals='{{"id": "{fa.id}"}}'
            hx-headers='{{"X-CSRFToken": "{csrf_token}"}}'
            hx-swap="outerHTML"
            onchange="this.style.backgroundColor = (this.options[this.selectedIndex].text.toLowerCase().includes('frais') ? 'rgba(245, 158, 11, 0.15)' : 'rgba(6, 182, 212, 0.15)');
                      this.style.borderColor = (this.options[this.selectedIndex].text.toLowerCase().includes('frais') ? '#f59e0b' : '#06b6d4');
                      this.style.color = (this.options[this.selectedIndex].text.toLowerCase().includes('frais') ? '#b45309' : '#0e7490');">
      {options}
    </select>
    """
    return HttpResponse(html)


@require_POST
def set_type_vente(request):
    """Endpoint HTMX pour changer le type de vente inline."""
    obj_id = request.POST.get('id')
    type_id = request.POST.get('type_vente')
    fv = get_object_or_404(FactureVente, pk=obj_id)
    
    if type_id:
        new_type = get_object_or_404(TypeFactureVente, pk=type_id)
        fv.type_facture = new_type
        fv.save()

    # Logique de couleur : Bleu pour Facture, Violet pour Acompte/Autre
    is_acompte = "acompte" in fv.type_facture.nom.lower()
    bg, border, text = ('rgba(168, 85, 247, 0.15)', '#a855f7', '#7e22ce') if is_acompte else ('rgba(6, 182, 212, 0.15)', '#06b6d4', '#0e7490')

    csrf_token = get_token(request)
    all_types = TypeFactureVente.objects.filter(active=True)
    
    options = "".join([
        f'<option value="{t.id}" style="background-color: white; color: #333;" {"selected" if fv.type_facture_id == t.id else ""}>{t.nom}</option>'
        for t in all_types
    ])

    html = f"""
    <select name="type_vente"
            style="font-size: .7rem; padding: 2px 12px; border-radius: 12px; cursor: pointer; font-weight: 700; appearance: none; -webkit-appearance: none; text-align: center; transition: all 0.2s; border: 1px solid {border}; color: {text}; background-color: {bg};"
            hx-post="/finance/set-type-vente/"
            hx-vals='{{"id": "{fv.id}"}}'
            hx-headers='{{"X-CSRFToken": "{csrf_token}"}}'
            hx-swap="outerHTML"
            onchange="this.style.backgroundColor = (this.options[this.selectedIndex].text.toLowerCase().includes('acompte') ? 'rgba(168, 85, 247, 0.15)' : 'rgba(6, 182, 212, 0.15)');
                      this.style.borderColor = (this.options[this.selectedIndex].text.toLowerCase().includes('acompte') ? '#a855f7' : '#06b6d4');
                      this.style.color = (this.options[this.selectedIndex].text.toLowerCase().includes('acompte') ? '#7e22ce' : '#0e7490');">
      {options}
    </select>
    """
    return HttpResponse(html)


@require_POST
def set_etude(request):
    """Endpoint HTMX pour changer l'étude d'un objet (Vente, Achat, BV)."""
    obj_type = request.POST.get('type')
    obj_id = request.POST.get('id')
    etude_id = request.POST.get('etude_id')
    etude_ref = request.POST.get('etude_ref')
    
    etude = None
    if etude_id and etude_id.isdigit():
        etude = Etude.objects.filter(pk=etude_id).first()
    
    if not etude and etude_ref:
        etude = Etude.objects.filter(reference__iexact=etude_ref.strip()).first()
    
    if obj_type == 'vente':
        obj = get_object_or_404(FactureVente, pk=obj_id)
    elif obj_type == 'achat':
        obj = get_object_or_404(FactureAchat, pk=obj_id)
    elif obj_type == 'bv':
        obj = get_object_or_404(BulletinVersement, pk=obj_id)
    else:
        return HttpResponse("Type inconnu", status=400)
    
    obj.etude = etude
    obj.save()
    
    return HttpResponse(etude.reference if etude else "—")


def achat_export_csv(request):
    """Exporte les factures d'achat en CSV selon une période et un mode de date."""
    from datetime import datetime
    from django.db.models.functions import Coalesce
    
    start_date_raw = request.GET.get('start_date')
    end_date_raw = request.GET.get('end_date')
    date_mode = request.GET.get('date_mode', 'operation')  # 'operation' or 'facture'
    
    qs = FactureAchat.objects.select_related('type_achat', 'ligne_budgetaire', 'operation')
    
    if start_date_raw and end_date_raw:
        try:
            start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            
            if date_mode == 'facture':
                # Si mode facture : filtrer sur date_reception avec fallback sur date_operation
                qs = qs.annotate(effective_date=Coalesce('date_reception', 'date_operation'))
                qs = qs.filter(effective_date__range=(start_date, end_date)).order_by('effective_date')
            else:
                qs = qs.filter(date_operation__range=(start_date, end_date)).order_by('date_operation')
        except ValueError:
            pass # Invalid dates, return unfiltered or handle as needed

    response = HttpResponse(content_type='text/csv')
    # Force UTF-8 BOM for Excel compatibility with French characters
    response.write('\ufeff'.encode('utf8'))
    
    filename = f"export_achats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response, delimiter=';')
    # Headers
    writer.writerow([
        'Référence', 'Lien Drive', 'Fournisseur', 'Type', 'Libellé', 
        'Bien/Service', 'Pays TVA', 'Date Facture', '[Vide]', 'HT', 
        'Taux TVA', 'TVA', 'TTC', 'Ligne Budget', 'Date Opération'
    ])
    
    for fa in qs:
        # Type : "Facture Fournisseur" ou "NDF"
        # On se base sur le nom du type ou le suffixe
        type_label = "Facture Fournisseur"
        if fa.type_achat and fa.type_achat.suffixe == 'NF':
            type_label = "NDF"
        elif fa.type_achat and "frais" in fa.type_achat.nom.lower():
            type_label = "NDF"
            
        # Pays TVA : TVA [XX]
        tva_country = f"TVA {fa.pays_tva.upper()}" if fa.pays_tva else ""
        
        # Bien/Service (Display name)
        cat_label = fa.get_categorisation_display() if fa.categorisation else ""
        
        writer.writerow([
            fa.numero or "",
            fa.lien_drive or "",
            fa.fournisseur or "",
            type_label,
            fa.libelle or "",
            cat_label,
            tva_country,
            fa.date_reception.strftime('%d/%m/%Y') if fa.date_reception else "",
            "", # Colonne vide
            f"{fa.montant_ht:.2f}".replace('.', ','),
            f"{fa.taux_tva:.2f}".replace('.', ','),
            f"{fa.montant_tva:.2f}".replace('.', ','),
            f"{fa.montant_ttc:.2f}".replace('.', ','),
            fa.ligne_budgetaire.nom if fa.ligne_budgetaire else "",
            fa.date_operation.strftime('%d/%m/%Y') if fa.date_operation else ""
        ])
        
    return response


def vente_export_csv(request):
    """Exporte les factures de vente en CSV selon une période et un mode de date."""
    from datetime import datetime, timedelta
    from django.db.models.functions import Coalesce
    
    start_date_raw = request.GET.get('start_date')
    end_date_raw = request.GET.get('end_date')
    date_mode = request.GET.get('date_mode', 'operation')  # 'operation' or 'facture'
    
    qs = FactureVente.objects.select_related('type_facture', 'etude', 'ligne_budgetaire', 'operation')
    
    if start_date_raw and end_date_raw:
        try:
            start_date = datetime.strptime(start_date_raw, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_raw, '%Y-%m-%d').date()
            
            if date_mode == 'facture':
                # Si mode facture : filtrer sur date_envoi avec fallback sur date_operation
                qs = qs.annotate(effective_date=Coalesce('date_envoi', 'date_operation'))
                qs = qs.filter(effective_date__range=(start_date, end_date)).order_by('effective_date')
            else:
                qs = qs.filter(date_operation__range=(start_date, end_date)).order_by('date_operation')
        except ValueError:
            pass

    response = HttpResponse(content_type='text/csv')
    response.write('\ufeff'.encode('utf8'))
    
    filename = f"export_ventes_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response, delimiter=';')
    # Headers : Référence, Tiers, Type, Étude, Libellé, TVA client, TVA, Lien Drive, Date Émission, Date Émission+30j, HT, [Vide], HT, Taux TVA, TVA, TTC, Date Op, Mois Décl, Ligne Budget
    writer.writerow([
        'Référence', 'Tiers', 'Type de facture', 'Réf Étude', 'Libellé', 
        'TVA client', 'TVA', 'Lien drive', 'Date d\'émission', 'Date d\'émission+30j', 
        'Valeur HT', '', 'Valeur HT (bis)', 'Taux TVA', 'TVA collectée', 
        'Valeur TTC', 'Date de l\'opération', 'Mois Déclaratif', 'Ligne de budget'
    ])
    
    MONTHS_FR = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril', 5: 'Mai', 6: 'Juin',
        7: 'Juillet', 8: 'Août', 9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }

    for fv in qs:
        # Calculs dates
        date_emiss_str = fv.date_envoi.strftime('%d/%m/%Y') if fv.date_envoi else ""
        date_30j_str = (fv.date_envoi + timedelta(days=30)).strftime('%d/%m/%Y') if fv.date_envoi else ""
        
        # Mois déclaratif (basé sur date d'opération)
        mois_decl = ""
        if fv.date_operation:
            mois_decl = f"{MONTHS_FR[fv.date_operation.month]} {fv.date_operation.year}"

        writer.writerow([
            fv.numero or "",
            fv.tiers or "",
            fv.type_facture.nom if fv.type_facture else "",
            fv.etude.reference if fv.etude else "",
            fv.libelle or "",
            "", # TVA client (vide)
            "", # TVA (vide)
            fv.lien_drive or "",
            date_emiss_str,
            date_30j_str,
            f"{fv.montant_ht:.2f}".replace('.', ','),
            "", # Colonne vide
            f"{fv.montant_ht:.2f}".replace('.', ','),
            f"{fv.taux_tva:.2f}".replace('.', ','),
            f"{fv.montant_tva:.2f}".replace('.', ','),
            f"{fv.montant_ttc:.2f}".replace('.', ','),
            fv.date_operation.strftime('%d/%m/%Y') if fv.date_operation else "",
            mois_decl,
            fv.ligne_budgetaire.nom if fv.ligne_budgetaire else ""
        ])
        
    return response
@require_POST
def update_invoice_field(request):
    """Mise à jour rapide d'un champ via HTMX (Numéro, Tiers ou Libellé)."""
    obj_type = request.POST.get('type')
    pk = request.POST.get('pk')
    field = request.POST.get('field')
    new_value = request.POST.get('value', '').strip()
    
    if obj_type == 'vente':
        obj = get_object_or_404(FactureVente, pk=pk)
        prefix = 'S' if obj.type_facture.est_subvention else 'FV'
    else:
        obj = get_object_or_404(FactureAchat, pk=pk)
        prefix = 'NF' if obj.type_achat.suffixe == 'NF' else 'A'

    try:
        if field == 'numero':
            if not new_value.startswith(prefix):
                return HttpResponse(f'<span class="text-danger" style="font-size:0.7rem">Prefix {prefix} requis</span>', status=200)
            obj.numero = new_value
        elif field == 'tiers':
            if obj_type == 'vente':
                obj.tiers = new_value
            else:
                obj.fournisseur = new_value
        elif field == 'libelle':
            obj.libelle = new_value
        elif field == 'commentaire':
            obj.commentaire = new_value
            
        obj.save()

        # Retourne le HTML correspondant au champ mis à jour
        if field == 'numero':
            return HttpResponse(f'<span class="font-mono font-bold" style="color:var(--color-primary);font-size:.75rem;cursor:pointer" onclick="enableQuickEdit(this, \'{obj_type}\', \'{obj.id}\', \'numero\')">{obj.numero}</span>')
        elif field == 'tiers' or field == 'libelle':
            # On retourne tout le bloc Tiers / Libellé pour que l'affichage reste synchro
            tiers_val = obj.tiers if obj_type == 'vente' else obj.fournisseur
            libelle_val = obj.libelle or 'Sans libellé'
            study_html = ""
            if obj_type == 'vente' and obj.etude:
                study_html = f'<div class="text-xs" style="color:var(--color-primary); font-size:0.65rem; font-weight:600">Étude: {obj.etude.reference}</div>'
            
            return HttpResponse(f'''
                <div style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer" onclick="enableQuickEdit(this, \'{obj_type}\', \'{obj.id}\', \'tiers\')">{tiers_val or '—'}</div>
                <div class="text-xs text-muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer" onclick="enableQuickEdit(this, \'{obj_type}\', \'{obj.id}\', \'libelle\')">{libelle_val}</div>
                {study_html}
            ''')
        elif field == 'commentaire':
            val = obj.commentaire or '—'
            return HttpResponse(f'<div class="text-xs text-muted" style="cursor:pointer; white-space:pre-wrap; word-break:break-word; width: 100%" onclick="enableQuickEdit(this, \'{obj_type}\', \'{obj.id}\', \'commentaire\')">{val}</div>')

    except IntegrityError:
        return HttpResponse(f'<span class="text-danger" style="font-size:0.7rem">Déjà utilisé</span>', status=200)
    except Exception as e:
        return HttpResponse(f'<span class="text-danger" style="font-size:0.7rem">Erreur</span>', status=200)

@require_POST
def set_taux_tva(request):
    """Endpoint HTMX pour changer le taux de TVA inline."""
    obj_type = request.POST.get('type')
    obj_id = request.POST.get('id')
    taux_val = request.POST.get('taux_tva')
    
    if obj_type == 'vente':
        obj = get_object_or_404(FactureVente, pk=obj_id)
        is_mixed = obj.taux_mixte
    else:
        obj = get_object_or_404(FactureAchat, pk=obj_id)
        is_mixed = obj.taux_compose

    if taux_val:
        new_taux = to_decimal(taux_val)
        obj.taux_tva = new_taux
        # Si pas en mode mixte, on recalcule HT/TVA depuis le TTC
        if not is_mixed:
            from finance.services import calculate_tva
            calcul = calculate_tva(obj.montant_ttc, new_taux)
            obj.montant_ht = calcul['ht']
            obj.montant_tva = calcul['tva']
        obj.save()

    # On retourne le nouveau taux et on déclenche un événement pour rafraîchir HT et TVA
    response = HttpResponse(f'<span class="font-mono" style="cursor:pointer" onclick="enableTvaEdit(this, \'{obj_type}\', \'{obj.id}\')">{obj.taux_tva:.0f}%</span>')
    response['HX-Trigger'] = f'refresh-invoice-{obj_type}-{obj.id}'
    return response

def refresh_invoice_cell(request):
    """Retourne la valeur HT ou TVA formatée d'une facture pour rafraîchir le listing."""
    obj_type = request.GET.get('type')
    pk = request.GET.get('pk')
    field = request.GET.get('field')
    
    if obj_type == 'vente':
        from finance.models import FactureVente
        obj = get_object_or_404(FactureVente, pk=pk)
    else:
        from finance.models import FactureAchat
        obj = get_object_or_404(FactureAchat, pk=pk)
        
    val = getattr(obj, f'montant_{field}', 0)
    from django.template.defaultfilters import floatformat
    return HttpResponse(floatformat(val, 2))


def ignored_operations_list(request):
    """Affiche les opérations marquées comme ignorées (virements internes)."""
    mois, annee = _get_filtres(request)
    
    qs = Operation.objects.filter(statut='ignored')
    qs = _appliquer_filtres(qs, mois, annee)
    
    # Tri par défaut inverse chronologique
    qs = qs.order_by('-date_operation', '-id')
    
    return render(request, 'finance/ignored_operations_list.html', {
        'operations': qs,
        'filtre_mois': mois,
        'filtre_annee': annee,
        'total_debit': sum((op.debit or 0) for op in qs),
        'total_credit': sum((op.credit or 0) for op in qs),
    })

@require_POST
def operation_reset(request, pk):
    """Remet une opération ignorée en statut 'pending'."""
    operation = get_object_or_404(Operation, pk=pk, statut='ignored')
    operation.statut = 'pending'
    operation.commentaire_ignoree = ""
    operation.save()
    messages.success(request, f"L'opération '{operation.libelle}' a été remise en attente de traitement.")
    return redirect('finance:ignored_operations_list')


def check_reference_exists(request):
    """Vérifie l'existence d'un numéro de facture (Ajax/HTMX)."""
    numero = request.GET.get('numero', '').strip()
    model_name = request.GET.get('model', 'achat')
    
    if not numero:
        return HttpResponse("")
        
    exists = False
    if model_name == 'achat':
        exists = FactureAchat.objects.filter(numero=numero).exists()
    elif model_name == 'vente':
        exists = FactureVente.objects.filter(numero=numero).exists()
    elif model_name == 'bv':
        exists = BulletinVersement.objects.filter(numero=numero).exists()
        
    if exists:
        return HttpResponse('<div class="flex items-center gap-1 text-danger font-bold" style="font-size:0.7rem"><i data-lucide="alert-triangle" width="12" height="12"></i> Déjà utilisé</div><script>lucide.createIcons();</script>')
    else:
        return HttpResponse('<div class="flex items-center gap-1 text-success font-bold" style="font-size:0.7rem"><i data-lucide="check-circle" width="12" height="12"></i> Disponible</div><script>lucide.createIcons();</script>')


def bv_generation(request):
    """
    Vue pour la génération d'un Bulletin de Versement (BV) : enregistre l'objet en BDD.
    """
    from datetime import date
    from .services import calculate_cotisations_urssaf, generate_numero_bv

    if request.method == 'POST':
        try:
            # Récupération des données du formulaire
            nb_jeh = to_decimal(request.POST.get('nb_jeh', '0'))
            retrib_par_jeh = to_decimal(request.POST.get('retribution_brute_par_jeh', '0'))
            
            # Calcul des cotisations (côté serveur pour sauvegarde)
            res = calculate_cotisations_urssaf(nb_jeh)
            
            # Création de l'objet BulletinVersement
            bv = BulletinVersement.objects.create(
                numero=request.POST.get('ref_bv'),
                date_operation=date.today(),
                intervenant_nom=request.POST.get('intervenant_nom', '').upper(),
                intervenant_prenom=request.POST.get('intervenant_prenom', ''),
                adresse=request.POST.get('adresse', ''),
                code_postal=request.POST.get('code_postal', ''),
                ville=request.POST.get('ville', ''),
                num_secu=request.POST.get('num_secu', ''),
                nom_mission=request.POST.get('nom_mission', ''),
                ref_rm=request.POST.get('ref_rm', ''),
                ref_avrm=request.POST.get('ref_avrm', ''),
                
                nb_jeh=nb_jeh,
                retribution_brute_par_jeh=retrib_par_jeh,
                assiette=res['assiette'],
                
                # Part Junior
                j_assurance_maladie=res['j_maladie'],
                j_accident_travail=res['j_at'],
                j_vieillesse_plafonnee=res['j_vp'],
                j_vieillesse_deplafonnee=res['j_vd'],
                j_allocations_familiales=res['j_af'],
                j_csg_deductible=res['j_csgd'],
                j_csg_non_deductible=res['j_csgnd'],
                total_junior=res['total_j'],
                
                # Part Étudiant
                e_assurance_maladie=res['e_maladie'],
                e_accident_travail=res['e_at'],
                e_vieillesse_plafonnee=res['e_vp'],
                e_vieillesse_deplafonnee=res['e_vd'],
                e_allocations_familiales=res['e_af'],
                e_csg_deductible=res['e_csgd'],
                e_csg_non_deductible=res['e_csgnd'],
                total_etudiant=res['total_e'],
                
                total_global=res['total_global'],
                commentaire=request.POST.get('commentaire', '')
            )
            
            messages.success(request, f"Le Bulletin de Versement {bv.numero} a été enregistré avec succès.")
            return redirect('finance:bv_generation')
            
        except Exception as e:
            messages.error(request, f"Erreur lors de l'enregistrement : {str(e)}")
            return redirect('finance:bv_generation')

    return render(request, 'finance/bv_generation.html', {
        'next_bv_numero': generate_numero_bv(date.today().year),
        'etudes': Etude.objects.filter(active=True).order_by('reference'),
        'param_j': ParametreCotisation.objects.filter(type_cotisant='junior').first(),
        'param_e': ParametreCotisation.objects.filter(type_cotisant='etudiant').first(),
    })

def bv_delete(request, pk):
    """Supprime un BV."""
    bv = get_object_or_404(BulletinVersement, pk=pk)
    num = bv.numero
    bv.delete()
    messages.success(request, f"Le Bulletin de Versement {num} a été supprimé.")
    return redirect('finance:bv_list')



