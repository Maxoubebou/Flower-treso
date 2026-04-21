from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import (
    LigneBudgetaire, TypeFactureVente, TypeAchat,
    ParametreTVA, ParametreCotisation, AutofillRule
)


def settings_index(request):
    """Page principale des paramètres."""
    return render(request, 'config_app/settings.html', {
        'lignes_budgetaires': LigneBudgetaire.objects.all().order_by('ordre', 'nom'),
        'types_facture_vente': TypeFactureVente.objects.all().order_by('ordre'),
        'types_achat': TypeAchat.objects.all().order_by('ordre'),
        'taux_tva': ParametreTVA.objects.all().order_by('ordre', 'taux'),
        'params_cotisations': ParametreCotisation.objects.all(),
        'autofill_rules': AutofillRule.objects.all().order_by('ordre', 'nom'),
    })


# ─── Taux TVA ────────────────────────────────────────────────────────────────

def taux_tva_update(request, pk):
    obj = get_object_or_404(ParametreTVA, pk=pk)
    if request.method == 'POST':
        try:
            from decimal import Decimal
            obj.taux = Decimal(request.POST['taux'])
            obj.libelle = request.POST.get('libelle', obj.libelle)
            obj.commentaire = request.POST.get('commentaire', obj.commentaire)
            obj.actif = 'actif' in request.POST
            obj.save()
            messages.success(request, f"Taux TVA {obj.taux}% mis à jour.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return redirect('config:settings_index')


def taux_tva_create(request):
    if request.method == 'POST':
        try:
            from decimal import Decimal
            ParametreTVA.objects.create(
                taux=Decimal(request.POST['taux']),
                libelle=request.POST['libelle'],
                commentaire=request.POST.get('commentaire', ''),
                ordre=int(request.POST.get('ordre', 99)),
            )
            messages.success(request, "Taux TVA créé.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return redirect('config:settings_index')


# ─── Cotisations URSSAF ──────────────────────────────────────────────────────

def cotisation_update(request, pk):
    obj = get_object_or_404(ParametreCotisation, pk=pk)
    if request.method == 'POST':
        try:
            from decimal import Decimal
            fields = [
                'base_urssaf', 'assurance_maladie', 'accident_travail',
                'vieillesse_plafonnee', 'vieillesse_deplafonnee',
                'allocations_familiales', 'csg_deductible', 'csg_non_deductible',
            ]
            for f in fields:
                if f in request.POST:
                    setattr(obj, f, Decimal(request.POST[f]))
            obj.save()
            messages.success(request, f"Paramètres cotisations {obj.get_type_cotisant_display()} mis à jour.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return redirect('config:settings_index')


# ─── Lignes budgétaires ──────────────────────────────────────────────────────

def ligne_budgetaire_create(request):
    if request.method == 'POST':
        try:
            LigneBudgetaire.objects.create(
                nom=request.POST['nom'].strip(),
                ordre=int(request.POST.get('ordre', 99)),
            )
            messages.success(request, "Ligne budgétaire créée.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return redirect('config:settings_index')


def ligne_budgetaire_toggle(request, pk):
    obj = get_object_or_404(LigneBudgetaire, pk=pk)
    obj.active = not obj.active
    obj.save()
    messages.success(request, f"Ligne « {obj.nom} » {'activée' if obj.active else 'désactivée'}.")
    return redirect('config:settings_index')


# ─── Types factures vente ────────────────────────────────────────────────────

def type_facture_vente_create(request):
    if request.method == 'POST':
        try:
            from decimal import Decimal
            TypeFactureVente.objects.create(
                nom=request.POST['nom'].strip(),
                code=request.POST['code'].strip().upper(),
                suffixe=request.POST['suffixe'],
                taux_tva_defaut=Decimal(request.POST.get('taux_tva_defaut', '20')),
                est_cotisation='est_cotisation' in request.POST,
                est_subvention='est_subvention' in request.POST,
                ordre=int(request.POST.get('ordre', 99)),
            )
            messages.success(request, "Type de facture créé.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return redirect('config:settings_index')


# ─── Types achat ─────────────────────────────────────────────────────────────

def type_achat_create(request):
    if request.method == 'POST':
        try:
            TypeAchat.objects.create(
                nom=request.POST['nom'].strip(),
                code=request.POST['code'].strip().upper(),
                suffixe=request.POST['suffixe'],
                ordre=int(request.POST.get('ordre', 99)),
            )
            messages.success(request, "Type d'achat créé.")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return redirect('config:settings_index')


# ─── Règles d'autocomplétion (AutofillRules) ─────────────────────────────────

def autofill_rule_create(request):
    """Crée une nouvelle règle d'autocomplétion."""
    from .models import AutofillRule, LigneBudgetaire
    from finance.models import Etude
    if request.method == 'POST':
        try:
            from decimal import Decimal
            taux_tva_raw = request.POST.get('taux_tva')
            lb_raw = request.POST.get('ligne_budgetaire')
            etude_raw = request.POST.get('etude')
            
            rule = AutofillRule(
                nom=request.POST.get('nom', '').strip(),
                mots_cles=request.POST.get('mots_cles', '').strip(),
                condition_type=request.POST.get('condition_type', 'OR'),
                type_operation=request.POST.get('type_operation', 'all'),
                fournisseur=request.POST.get('fournisseur', '').strip(),
                libelle_defaut=request.POST.get('libelle_defaut', '').strip(),
                pays_tva=request.POST.get('pays_tva', '') or '',
                categorisation_achat=request.POST.get('categorisation_achat', '') or '',
                ordre=int(request.POST.get('ordre', 0)),
            )

            if taux_tva_raw:
                rule.taux_tva = Decimal(taux_tva_raw)
            if lb_raw:
                rule.ligne_budgetaire = LigneBudgetaire.objects.get(pk=lb_raw)
            if etude_raw:
                rule.etude = Etude.objects.get(pk=etude_raw)

            rule.save()
            messages.success(request, f"Règle « {rule.nom} » créée avec succès.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la création de la règle : {e}")
            
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    return redirect(next_url if next_url else 'config:settings_index')

def autofill_rule_delete(request, pk):
    """Supprime une règle d'autocomplétion."""
    from .models import AutofillRule
    rule = get_object_or_404(AutofillRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        messages.success(request, f"Règle « {rule.nom} » supprimée.")
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    return redirect(next_url if next_url else 'config:settings_index')
