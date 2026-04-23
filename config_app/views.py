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
        'param_j': ParametreCotisation.objects.filter(type_cotisant='junior').first(),
        'param_e': ParametreCotisation.objects.filter(type_cotisant='etudiant').first(),
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

def cotisation_unified_update(request):
    """Mise à jour globale des taux URSSAF et recalcul de tous les BV."""
    if request.method == 'POST':
        try:
            from decimal import Decimal
            from finance.models import BulletinVersement
            from finance.services import calculate_cotisations_urssaf
            
            p_j = ParametreCotisation.objects.get(type_cotisant='junior')
            p_e = ParametreCotisation.objects.get(type_cotisant='etudiant')
            
            fields = [
                'base_urssaf', 'assurance_maladie', 'accident_travail',
                'vieillesse_plafonnee', 'vieillesse_deplafonnee',
                'allocations_familiales', 'csg_deductible', 'csg_non_deductible'
            ]
            
            for f in fields:
                # Junior values
                if f"junior_{f}" in request.POST:
                    setattr(p_j, f, Decimal(request.POST[f"junior_{f}"].replace(',', '.')))
                # Etudiant values
                if f"etudiant_{f}" in request.POST:
                    setattr(p_e, f, Decimal(request.POST[f"etudiant_{f}"].replace(',', '.')))
            
            p_j.save()
            p_e.save()
            
            # Recalculer TOUS les BV existants
            bvs = BulletinVersement.objects.all()
            for bv in bvs:
                cotis = calculate_cotisations_urssaf(bv.nb_jeh)
                bv.assiette = cotis['assiette']
                # Junior
                bv.j_assurance_maladie = cotis['j_maladie']
                bv.j_accident_travail = cotis['j_at']
                bv.j_vieillesse_plafonnee = cotis['j_vp']
                bv.j_vieillesse_deplafonnee = cotis['j_vd']
                bv.j_allocations_familiales = cotis['j_af']
                bv.j_csg_deductible = cotis['j_csgd']
                bv.j_csg_non_deductible = cotis['j_csgnd']
                bv.total_junior = cotis['total_j']
                # Etudiant
                bv.e_assurance_maladie = cotis['e_maladie']
                bv.e_accident_travail = cotis['e_at']
                bv.e_vieillesse_plafonnee = cotis['e_vp']
                bv.e_vieillesse_deplafonnee = cotis['e_vd']
                bv.e_allocations_familiales = cotis['e_af']
                bv.e_csg_deductible = cotis['e_csgd']
                bv.e_csg_non_deductible = cotis['e_csgnd']
                bv.total_etudiant = cotis['total_e']
                
                bv.total_global = cotis['total_global']
                bv.save()
                
            messages.success(request, f"Taux URSSAF mis à jour et {bvs.count()} bulletins synchronisés.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la mise à jour des taux : {e}")
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
            
            nom_rule = request.POST.get('nom', '').strip()
            defaults_data = {
                'mots_cles': request.POST.get('mots_cles', '').strip(),
                'condition_type': request.POST.get('condition_type', 'OR'),
                'type_operation': request.POST.get('type_operation', 'all'),
                'fournisseur': request.POST.get('fournisseur', '').strip(),
                'libelle_defaut': request.POST.get('libelle_defaut', '').strip(),
                'pays_tva': request.POST.get('pays_tva', '') or '',
                'categorisation_achat': request.POST.get('categorisation_achat', '') or '',
                'ordre': int(request.POST.get('ordre', 0)),
                'taux_tva': None,
                'ligne_budgetaire': None,
                'etude': None,
            }

            if taux_tva_raw:
                defaults_data['taux_tva'] = Decimal(taux_tva_raw)
            if lb_raw:
                defaults_data['ligne_budgetaire'] = LigneBudgetaire.objects.get(pk=lb_raw)
            if etude_raw:
                defaults_data['etude'] = Etude.objects.get(pk=etude_raw)

            rule, created = AutofillRule.objects.update_or_create(
                nom=nom_rule,
                defaults=defaults_data
            )

            if created:
                messages.success(request, f"Nouvelle règle « {rule.nom} » créée.")
            else:
                messages.success(request, f"Règle « {rule.nom} » mise à jour avec succès.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la sauvegarde de la règle : {e}")
            
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
