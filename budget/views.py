from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, F
from django.contrib import messages
import re

from .models import BudgetSubCategory, BudgetItem
from config_app.models import LigneBudgetaire
from finance.models import FactureVente, FactureAchat, BulletinVersement
from flower_treso.utils import to_decimal, evaluate_budget_formula

def budget_dashboard(request):
    """Vue principale du budget avec calculs en temps réel et support du nesting."""
    selected_year = request.GET.get('year')
    
    # On récupère toutes les sous-catégories
    all_subcats = BudgetSubCategory.objects.prefetch_related('items__ligne_budgetaire').all()
    
    # Préchauffage des items (Realised sum)
    for sc in all_subcats:
        for item in sc.items.all():
            lb = item.ligne_budgetaire
            realise = 0
            if sc.group == 'produit':
                res = FactureVente.objects.filter(ligne_budgetaire=lb).aggregate(total=Sum('montant_ht'))
                realise = res['total'] or 0
            else:
                res_achats = FactureAchat.objects.filter(ligne_budgetaire=lb).aggregate(total=Sum('montant_ht'))
                realise_achats = res_achats['total'] or 0
                if "cotisation" in lb.nom.lower() and "urssaf" in lb.nom.lower():
                    res_bv = BulletinVersement.objects.filter(ligne_budgetaire=lb).aggregate(total=Sum('total_cotisations_junior'))
                else:
                    res_bv = BulletinVersement.objects.filter(ligne_budgetaire=lb).aggregate(
                        total=Sum(F('nb_jeh') * F('retribution_brute_par_jeh'))
                    )
                realise_bv = res_bv['total'] or 0
                realise = realise_achats + realise_bv
            
            item.realise = realise
            item.dispo_moyen = item.scenario_moyen - realise
            # Progrès (gamefié)
            if item.scenario_moyen > 0:
                item.progress_percent = round((realise / item.scenario_moyen) * 100)
                item.over_budget = realise > item.scenario_moyen
            else:
                item.progress_percent = 0
                item.over_budget = False

    # On injecte les IDs et on récupère les objets en liste pour conserver les attributs
    all_subcats_list, items_flat = _inject_ids(all_subcats)
    
    # Organisation hiérarchique
    produits_roots = [sc for sc in all_subcats_list if sc.group == 'produit' and sc.parent_id is None]
    charges_roots = [sc for sc in all_subcats_list if sc.group == 'charge' and sc.parent_id is None]

    # Calcul des budgets par catégorie
    for sc in all_subcats_list:
        sc.total_moyen = sum(item.scenario_moyen for item in sc.prefetched_items)
        child_total = 0
        for child in sc.children.all():
            # Attention: children.items might not have IDs if not injected
            # Mais ici on utilise juste pour le total
            child_total += sum(item.scenario_moyen for item in child.items.all())
        sc.total_moyen_cumule = sc.total_moyen + child_total

    # Calcul des totaux globaux
    totals = {
        'visé': sum(item.scenario_moyen for item in items_flat if item.subcategory.group == 'produit'),
        'réalisé_p': sum(item.realise for item in items_flat if item.subcategory.group == 'produit'),
        'réalisé_c': sum(item.realise for item in items_flat if item.subcategory.group == 'charge'),
    }
    totals['solde_prevu'] = totals['visé'] - sum(item.scenario_moyen for item in items_flat if item.subcategory.group == 'charge')
    totals['solde_reel'] = totals['réalisé_p'] - totals['réalisé_c']

    # ─── Graphique d'évolution ─────────────────
    from django.db.models.functions import TruncWeek, TruncMonth
    import json
    from datetime import datetime, date

    # Filtrage par année pour le graphique
    ventes_qs = FactureVente.objects.all()
    achats_qs = FactureAchat.objects.all()
    bv_qs = BulletinVersement.objects.all()

    # On récupère les années disponibles dynamiquement
    v_years = set(FactureVente.objects.dates('date_operation', 'year').values_list('date_operation__year', flat=True))
    a_years = set(FactureAchat.objects.dates('date_operation', 'year').values_list('date_operation__year', flat=True))
    b_years = set(BulletinVersement.objects.dates('date_operation', 'year').values_list('date_operation__year', flat=True))
    available_years = sorted(list(v_years | a_years | b_years), reverse=True)

    is_year_view = False
    if selected_year and selected_year.isdigit():
        year_int = int(selected_year)
        ventes_qs = ventes_qs.filter(date_operation__year=year_int)
        achats_qs = achats_qs.filter(date_operation__year=year_int)
        bv_qs = bv_qs.filter(date_operation__year=year_int)
        is_year_view = True

    chart_income = []
    chart_expenses = []
    chart_labels = []

    if is_year_view:
        # Vue par mois (12 mois fixes)
        chart_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"]
        
        # Agrégation par mois
        ventes_data = ventes_qs.annotate(month=TruncMonth('date_operation')) \
            .values('month').annotate(total=Sum('montant_ht')).order_by('month')
        achats_data = achats_qs.annotate(month=TruncMonth('date_operation')) \
            .values('month').annotate(total=Sum('montant_ht')).order_by('month')
        bv_data = bv_qs.annotate(month=TruncMonth('date_operation')) \
            .values('month').annotate(total=Sum(F('nb_jeh') * F('retribution_brute_par_jeh') + F('total_cotisations_junior'))) \
            .order_by('month')
            
        cumul_i = 0
        cumul_e = 0
        for m in range(1, 13):
            v_val = next((v['total'] for v in ventes_data if v['month'] and v['month'].month == m), 0)
            a_val = next((a['total'] for a in achats_data if a['month'] and a['month'].month == m), 0)
            b_val = next((b['total'] for b in bv_data if b['month'] and b['month'].month == m), 0)
            
            cumul_i += float(v_val or 0)
            cumul_e += float((a_val or 0) + (b_val or 0))
            
            chart_income.append(round(cumul_i, 2))
            chart_expenses.append(round(cumul_e, 2))
    else:
        # Vue "Toutes les années" -> Hebdomadaire (CONTINUE)
        from datetime import timedelta
        
        # Récupération des données brutes par semaine
        ventes_data = ventes_qs.annotate(week=TruncWeek('date_operation')) \
            .values('week').annotate(total=Sum('montant_ht')).order_by('week')
        achats_data = achats_qs.annotate(week=TruncWeek('date_operation')) \
            .values('week').annotate(total=Sum('montant_ht')).order_by('week')
        bv_data = bv_qs.annotate(week=TruncWeek('date_operation')) \
            .values('week').annotate(total=Sum(F('nb_jeh') * F('retribution_brute_par_jeh') + F('total_cotisations_junior'))) \
            .order_by('week')

        # Trouver les bornes
        all_raw_weeks = [v['week'] for v in ventes_data if v['week']] + \
                         [a['week'] for a in achats_data if a['week']] + \
                         [b['week'] for b in bv_data if b['week']]
        
        if all_raw_weeks:
            min_w = min(all_raw_weeks)
            max_w = max(all_raw_weeks)
            
            # Conversion en dict pour perfs O(1)
            v_dict = {(v['week'].date() if hasattr(v['week'], 'date') else v['week']): v['total'] for v in ventes_data if v['week']}
            a_dict = {(a['week'].date() if hasattr(a['week'], 'date') else a['week']): a['total'] for a in achats_data if a['week']}
            b_dict = {(b['week'].date() if hasattr(b['week'], 'date') else b['week']): b['total'] for b in bv_data if b['week']}
            
            # Générer TOUTES les semaines entre min et max
            current_w = min_w
            if isinstance(current_w, datetime): current_w = current_w.date()
            if isinstance(max_w, datetime): max_w = max_w.date()
            
            cumul_i = 0
            cumul_e = 0
            
            while current_w <= max_w:
                v_val = v_dict.get(current_w, 0)
                a_val = a_dict.get(current_w, 0)
                b_val = b_dict.get(current_w, 0)
                
                cumul_i += float(v_val or 0)
                cumul_e += float((a_val or 0) + (b_val or 0))
                
                chart_labels.append(current_w.strftime('%d/%m/%y'))
                chart_income.append(round(cumul_i, 2))
                chart_expenses.append(round(cumul_e, 2))
                
                current_w += timedelta(days=7)
        else:
            chart_labels = ["Pas de données"]
            chart_income = [0]
            chart_expenses = [0]

    chart_data = {
        'labels': chart_labels,
        'income': chart_income,
        'expenses': chart_expenses,
    }

    context = {
        'produits': produits_roots,
        'charges': charges_roots,
        'totals': totals,
        'all_subcats': all_subcats,
        'lignes_libres': LigneBudgetaire.objects.filter(active=True).exclude(budget_items__isnull=False).order_by('nom'),
        'chart_data_json': json.dumps(chart_data),
        'available_years': available_years,
        'selected_year': selected_year,
    }

    if request.headers.get('HX-Request') and request.GET.get('chart_only'):
        return render(request, 'budget/partials/dashboard_chart.html', context)
        
    return render(request, 'budget/dashboard.html', context)

@require_POST
def budget_item_update(request, pk):
    """Mise à jour inline via HTMX d'une valeur de scénario ou d'une formule."""
    item = get_object_or_404(BudgetItem, pk=pk)
    field = request.POST.get('field')
    value_raw = request.POST.get('value', '').strip()
    
    if field == 'scenario_moyen':
        # On détecte si c'est une formule
        if value_raw.startswith('=') or '[' in value_raw or re.search(r'[A-Z]{2,}\d+', value_raw):
            item.formula_moyen = value_raw
        else:
            item.formula_moyen = None
            item.scenario_moyen = to_decimal(value_raw)
        
        item.save()
        recalculate_budget_items()
        item.refresh_from_db()
        
    elif field == 'nom':
        new_name = value_raw
        # Vérification de doublon
        if LigneBudgetaire.objects.filter(nom=new_name).exclude(pk=item.ligne_budgetaire.pk).exists():
            return HttpResponse(
                f'Une ligne nommée "{new_name}" existe déjà.',
                status=409
            )
        lb = item.ligne_budgetaire
        lb.nom = new_name
        lb.save()
        
    elif field in ['scenario_bas', 'scenario_haut']:
        value = to_decimal(value_raw)
        setattr(item, field, value)
        item.save()
        
    elif field == 'commentaire':
        item.commentaire = value_raw
        item.save()
    
    # On ré-injecte les IDs pour le rendu de la ligne
    all_subcats = BudgetSubCategory.objects.prefetch_related('items__ligne_budgetaire', 'subcategory').all()
    _, items_with_ids = _inject_ids(all_subcats)
    
    # On retrouve l'item injecté pour avoir son short_id, puis on calcule son réalisé
    for it in items_with_ids:
        if it.pk == item.pk:
            # S'assurer que les relations nécessaires sont chargées pour _compute_realise
            # Note: _inject_ids a déjà chargé ligne_budgetaire et subcategory via l'it actuel
            _compute_realise(it)
            return render(request, 'budget/partials/budget_row_item.html', {'item': it})

    # Fallback pour s'assurer que l'objet direct a aussi son réalisé calculé
    _compute_realise(item)
    return render(request, 'budget/partials/budget_row_item.html', {'item': item})


def _compute_realise(item):
    """Calcule item.realise en fonction de son groupe de catégorie."""
    lb = item.ligne_budgetaire
    group = item.subcategory.group
    if group == 'produit':
        res = FactureVente.objects.filter(ligne_budgetaire=lb).aggregate(total=Sum('montant_ht'))
        item.realise = res['total'] or 0
    else:
        res_achats = FactureAchat.objects.filter(ligne_budgetaire=lb).aggregate(total=Sum('montant_ht'))
        realise_achats = res_achats['total'] or 0
        if "cotisation" in lb.nom.lower() and "urssaf" in lb.nom.lower():
            res_bv = BulletinVersement.objects.filter(ligne_budgetaire=lb).aggregate(total=Sum('total_cotisations_junior'))
        else:
            res_bv = BulletinVersement.objects.filter(ligne_budgetaire=lb).aggregate(
                total=Sum(F('nb_jeh') * F('retribution_brute_par_jeh'))
            )
        realise_bv = res_bv['total'] or 0
        item.realise = realise_achats + realise_bv


def _inject_ids(subcats):
    """Calcule et injecte les short_ids dans les items des catégories."""
    prefixes = {}
    items_flat = []
    subcats_list = list(subcats)
    for sc in subcats_list:
        # Base: les 2 premières lettres alphanum
        base = "".join(filter(str.isalnum, sc.name))[:2].upper()
        if not base: base = "XX"
        prefix = base
        i = 2
        while prefix in prefixes.values():
            prefix = f"{base}{i}"
            i += 1
        prefixes[sc.id] = prefix
        
        sc.prefetched_items = list(sc.items.all())
        for idx, item in enumerate(sc.prefetched_items, 1):
            item.short_id = f"{prefix}{idx}"
            items_flat.append(item)
    return subcats_list, items_flat
    
    return HttpResponse("Erreur", status=400)


def recalculate_budget_items():
    """
    Recalcule toutes les lignes budgétaires ayant une formule.
    Gère les dépendances en plusieurs passes.
    """
    # On récupère tout pour avoir le contexte complet (noms + IDs)
    all_subcats = BudgetSubCategory.objects.prefetch_related('items__ligne_budgetaire').all()
    
    # On fait au maximum N passes pour gérer les cascades de formules
    items_flat = []
    for sc in all_subcats:
        items_flat.extend(list(sc.items.all()))
        
    max_passes = len(items_flat)
    for _ in range(max_passes):
        has_changed = False
        
        # On génère le contexte (IDs + Noms) à chaque passe via le helper
        _, all_items = _inject_ids(all_subcats)
        context = {}
        for it in all_items:
            val = float(it.scenario_moyen)
            context[it.ligne_budgetaire.nom] = val
            context[it.short_id] = val
        
        for it in items_flat:
            if it.formula_moyen:
                new_val = evaluate_budget_formula(it.formula_moyen, context)
                if new_val != it.scenario_moyen:
                    it.scenario_moyen = new_val
                    it.save(update_fields=['scenario_moyen'])
                    has_changed = True
        
        if not has_changed:
            break

@require_POST
def add_subcategory(request):
    name = request.POST.get('name')
    group = request.POST.get('group')
    parent_id = request.POST.get('parent_id')
    if name and group:
        BudgetSubCategory.objects.create(
            name=name, 
            group=group, 
            parent_id=parent_id if parent_id else None
        )
    return redirect('budget:dashboard')

@require_POST
def delete_subcategory(request, pk):
    sc = get_object_or_404(BudgetSubCategory, pk=pk)
    sc.delete()
    return redirect('budget:dashboard')

@require_POST
def add_budget_line(request):
    sc_id = request.POST.get('subcategory_id')
    lb_ids = request.POST.getlist('ligne_budgetaire_ids')
    new_lb_nom = request.POST.get('new_lb_nom')
    
    if sc_id:
        # Cas 1 : Création d'une nouvelle ligne globale
        if new_lb_nom:
            lb, created = LigneBudgetaire.objects.get_or_create(nom=new_lb_nom)
            BudgetItem.objects.get_or_create(subcategory_id=sc_id, ligne_budgetaire=lb)
        
        # Cas 2 : Sélection de lignes existantes
        if lb_ids:
            for lb_id in lb_ids:
                BudgetItem.objects.get_or_create(subcategory_id=sc_id, ligne_budgetaire_id=lb_id)
                
    return redirect('budget:dashboard')

@require_POST
def delete_ligne_budgetaire(request, pk):
    """Suppression globale d'une ligne budgétaire."""
    lb = get_object_or_404(LigneBudgetaire, pk=pk)
    lb.delete()
    return redirect('budget:dashboard')

@require_POST
def delete_line(request, pk):
    item = get_object_or_404(BudgetItem, pk=pk)
    item.delete()
    return redirect('budget:dashboard')

@require_POST
def move_subcategory(request, pk, direction):
    """Déplace une sous-catégorie vers le haut ou le bas au sein de son groupe."""
    sc = get_object_or_404(BudgetSubCategory, pk=pk)
    # On récupère toutes les catégories sœurs (même groupe, même parent)
    siblings = list(BudgetSubCategory.objects.filter(group=sc.group, parent=sc.parent).order_by('ordre', 'name'))
    
    # Normalisation des ordres pour assurer une suite logique stable
    for i, sibling in enumerate(siblings):
        if sibling.ordre != i:
            sibling.ordre = i
            sibling.save(update_fields=['ordre'])
            
    current_index = next(i for i, sib in enumerate(siblings) if sib.pk == sc.pk)
    
    target_index = None
    if direction == 'up' and current_index > 0:
        target_index = current_index - 1
    elif direction == 'down' and current_index < len(siblings) - 1:
        target_index = current_index + 1
        
    if target_index is not None:
        other = siblings[target_index]
        # Swap des ordres
        sc.ordre, other.ordre = other.ordre, sc.ordre
        sc.save(update_fields=['ordre'])
        other.save(update_fields=['ordre'])
        
    if request.headers.get('HX-Request'):
        # On renvoie tout le dashboard, HTMX fera le hx-select="body" 
        # (ou mieux, on pourrait extraire juste la partie nécessaire ici, 
        # mais hx-select sur le client est plus simple pour l'instant)
        return budget_dashboard(request)
        
    return redirect('budget:dashboard')
