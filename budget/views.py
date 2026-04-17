from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, F
from django.contrib import messages

from .models import BudgetSubCategory, BudgetItem
from config_app.models import LigneBudgetaire
from finance.models import FactureVente, FactureAchat, BulletinVersement
from flower_treso.utils import to_decimal, evaluate_budget_formula

def budget_dashboard(request):
    """Vue principale du budget avec calculs en temps réel et support du nesting."""
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

    # Organisation hiérarchique : Group (Part) -> Root SubCat -> Child SubCat
    produits_roots = all_subcats.filter(group='produit', parent__isnull=True)
    charges_roots = all_subcats.filter(group='charge', parent__isnull=True)

    # Calcul des budgets par catégorie
    for sc in all_subcats:
        sc.total_moyen = sum(item.scenario_moyen for item in sc.items.all())
        # Si c'est un parent, on peut aussi additionner ses enfants pour l'affichage ?
        # Le user demande "le budget associé à une catégorie". 
        # On va afficher le total de la section (sc + ses items + ses enfants).
        child_total = 0
        for child in sc.children.all():
            child_total += sum(item.scenario_moyen for item in child.items.all())
        sc.total_moyen_cumule = sc.total_moyen + child_total

    # Calcul des totaux globaux pour le bandeau
    totals = {
        'visé': sum(item.scenario_moyen for sc in all_subcats if sc.group == 'produit' for item in sc.items.all()),
        'réalisé_p': sum(item.realise for sc in all_subcats if sc.group == 'produit' for item in sc.items.all()),
        'réalisé_c': sum(item.realise for sc in all_subcats if sc.group == 'charge' for item in sc.items.all()),
    }
    # Solde prévu et réel
    totals['solde_prevu'] = totals['visé'] - sum(item.scenario_moyen for sc in all_subcats if sc.group == 'charge' for item in sc.items.all())
    totals['solde_reel'] = totals['réalisé_p'] - totals['réalisé_c']

    # ─── Graphique d'évolution (Hebdomadaire) ─────────────────
    from django.db.models.functions import TruncWeek
    import json
    from datetime import date

    # On récupère les ventes par semaine
    ventes_semaine = FactureVente.objects.annotate(week=TruncWeek('date_operation')) \
        .values('week').annotate(total=Sum('montant_ht')).order_by('week')
    
    # On récupère les achats par semaine
    achats_semaine = FactureAchat.objects.annotate(week=TruncWeek('date_operation')) \
        .values('week').annotate(total=Sum('montant_ht')).order_by('week')
    
    # On récupère les BV par semaine (brut + cotisations junior)
    bv_semaine = BulletinVersement.objects.annotate(week=TruncWeek('date_operation')) \
        .values('week').annotate(total=Sum(F('nb_jeh') * F('retribution_brute_par_jeh') + F('total_cotisations_junior'))) \
        .order_by('week')

    # Fusion des données hebdomadaires
    all_weeks = sorted(list(set(
        [v['week'] for v in ventes_semaine] + 
        [a['week'] for a in achats_semaine] + 
        [b['week'] for b in bv_semaine]
    )))

    chart_labels = [w.strftime('%d/%m') for w in all_weeks]
    chart_income = []
    chart_expenses = []
    
    cumul_i = 0
    cumul_e = 0
    
    for w in all_weeks:
        v_val = next((v['total'] for v in ventes_semaine if v['week'] == w), 0)
        a_val = next((a['total'] for a in achats_semaine if a['week'] == w), 0)
        b_val = next((b['total'] for b in bv_semaine if b['week'] == w), 0)
        
        cumul_i += float(v_val)
        cumul_e += float(a_val + b_val)
        
        chart_income.append(cumul_i)
        chart_expenses.append(cumul_e)

    chart_data = {
        'labels': chart_labels,
        'income': chart_income,
        'expenses': chart_expenses,
    }

    return render(request, 'budget/dashboard.html', {
        'produits': produits_roots,
        'charges': charges_roots,
        'totals': totals,
        'all_subcats': all_subcats,
        'lignes_libres': LigneBudgetaire.objects.filter(active=True).exclude(budget_items__isnull=False).order_by('nom'),
        'chart_data_json': json.dumps(chart_data),
    })

@require_POST
def budget_item_update(request, pk):
    """Mise à jour inline via HTMX d'une valeur de scénario ou d'une formule."""
    item = get_object_or_404(BudgetItem, pk=pk)
    field = request.POST.get('field')
    value_raw = request.POST.get('value', '').strip()
    
    if field == 'scenario_moyen':
        # On détecte si c'est une formule
        if value_raw.startswith('=') or '[' in value_raw:
            item.formula_moyen = value_raw
            # On laisse le champ scenario_moyen tel quel pour l'instant, 
            # il sera mis à jour par recalculate_budget_items
        else:
            item.formula_moyen = None
            item.scenario_moyen = to_decimal(value_raw)
        
        item.save()
        
        # Recalcul global pour mettre à jour les dépendances
        recalculate_budget_items()
        
        # On recharge l'item pour avoir la valeur calculée
        item.refresh_from_db()
        return render(request, 'budget/partials/budget_row_item.html', {'item': item})
        
    elif field in ['scenario_bas', 'scenario_haut']:
        value = to_decimal(value_raw)
        setattr(item, field, value)
        item.save()
        return render(request, 'budget/partials/budget_row_item.html', {'item': item})
        
    elif field == 'commentaire':
        item.commentaire = value_raw
        item.save()
        return render(request, 'budget/partials/budget_row_item.html', {'item': item})
    
    return HttpResponse("Erreur", status=400)


def recalculate_budget_items():
    """
    Recalcule toutes les lignes budgétaires ayant une formule.
    Gère les dépendances en plusieurs passes.
    """
    items = list(BudgetItem.objects.all().select_related('ligne_budgetaire'))
    
    # On fait au maximum N passes pour gérer les cascades de formules
    max_passes = len(items)
    for _ in range(max_passes):
        has_changed = False
        # Context : nom -> valeur scenario_moyen
        context = {it.ligne_budgetaire.nom: float(it.scenario_moyen) for it in items}
        
        for it in items:
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
