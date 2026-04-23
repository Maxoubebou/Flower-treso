from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum, F
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.middleware.csrf import get_token

from .models import FactureVente, BulletinVersement, FactureAchat, Etude
from config_app.models import TypeFactureVente, TypeAchat, LigneBudgetaire, ParametreTVA, ParametreCotisation
from flower_treso.utils import to_decimal


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

    from finance.models import Etude as EtudeModel
    return render(request, 'finance/vente_form.html', {
        'facture': fv,
        'types_facture_vente': TypeFactureVente.objects.filter(active=True),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True),
        'etudes': EtudeModel.objects.filter(active=True).order_by('reference'),
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
        'current_sort': request.GET.get('sort'),
        'current_order': request.GET.get('order', 'asc'),
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
            ligne_bud_pk = request.POST.get('ligne_budgetaire')

            bv.etude = Etude.objects.get(pk=etude_pk) if etude_pk else None
            bv.ligne_budgetaire = LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None
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
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True, budget_items__isnull=False).distinct(),
        'cotisations_params': ParametreCotisation.objects.all(),
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
