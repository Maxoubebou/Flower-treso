from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from .models import Operation, ImportBatch
from .services import parse_csv
from flower_treso.utils import to_decimal



def import_csv(request):
    """Vue d'import du fichier CSV bancaire."""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, "Veuillez sélectionner un fichier CSV.")
            return redirect('operations:import_csv')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Le fichier doit être au format CSV.")
            return redirect('operations:import_csv')

        try:
            content = csv_file.read()
            batch, ops, errors = parse_csv(content, filename=csv_file.name)
            if errors:
                for err in errors:
                    messages.warning(request, err)
            messages.success(
                request,
                f"{len(ops)} opération(s) importée(s) depuis « {csv_file.name} »."
            )
            return redirect('operations:process_list')
        except Exception as e:
            messages.error(request, f"Erreur lors de l'import : {e}")
            return redirect('operations:import_csv')

    # GET — afficher les imports récents
    recent_batches = ImportBatch.objects.order_by('-created_at')[:5]
    pending_count = Operation.objects.filter(statut='pending').count()
    return render(request, 'operations/import_csv.html', {
        'recent_batches': recent_batches,
        'pending_count': pending_count,
    })


def process_list(request):
    """Liste des opérations en attente de traitement."""
    # Gestion du mois (Multi-sélection)
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
        mois = request.session.get('filtre_mois', [])

    # Gestion de l'année
    if 'annee' in request.GET:
        annee = request.GET.get('annee')
        request.session['filtre_annee'] = annee
    else:
        annee = request.session.get('filtre_annee', '2025')

    statut = request.GET.get('statut', 'pending')

    qs = Operation.objects.select_related('import_batch')
    if statut:
        qs = qs.filter(statut=statut)
    
    if mois:
        qs = qs.filter(date_operation__month__in=[int(m) for m in mois])
    if annee:
        qs = qs.filter(date_operation__year=int(annee))

    # Années disponibles pour le filtre
    from django.db.models import Max, Min
    dates = Operation.objects.aggregate(min=Min('date_operation'), max=Max('date_operation'))

    return render(request, 'operations/process_list.html', {
        'operations': qs.order_by('date_operation', 'id'),
        'filtre_mois': mois,
        'filtre_annee': annee,
        'filtre_statut': statut,
        'dates': dates,
    })


def process_operation(request, operation_id):
    """Traitement détaillé d'une opération."""
    operation = get_object_or_404(Operation, pk=operation_id)

    from config_app.models import TypeFactureVente, TypeAchat, LigneBudgetaire, ParametreTVA
    from finance.models import Etude

    context = {
        'operation': operation,
        'types_facture_vente': TypeFactureVente.objects.filter(active=True).order_by('ordre'),
        'types_achat': TypeAchat.objects.filter(active=True).order_by('ordre'),
        'lignes_budgetaires': LigneBudgetaire.objects.filter(active=True).order_by('ordre'),
        'taux_tva_disponibles': ParametreTVA.objects.filter(actif=True).order_by('ordre'),
        'etudes': Etude.objects.filter(active=True).order_by('reference'),
    }

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'ignorer':
            operation.statut = 'ignored'
            operation.commentaire_ignoree = request.POST.get('commentaire', '')
            operation.save()
            messages.success(request, f"Opération « {operation.libelle} » ignorée.")
            return _redirect_next(operation)

        elif action == 'vente':
            return _process_vente(request, operation)

        elif action == 'bv':
            return _process_bv(request, operation)

        elif action == 'achat':
            return _process_achat(request, operation)

    return render(request, 'operations/process_operation.html', context)


def _redirect_next(operation, to_next=True):
    """Redirige vers la prochaine opération pending (si to_next=True) ou la liste."""
    if not to_next:
        return redirect('operations:process_list')

    next_op = Operation.objects.filter(
        statut='pending',
        date_operation__gte=operation.date_operation,
        id__gt=operation.id
    ).first()
    if next_op:
        return redirect('operations:process_operation', operation_id=next_op.pk)
    return redirect('operations:process_list')


def _process_vente(request, operation):
    """Traite une opération crédit en facture de vente."""
    from finance.models import FactureVente
    from finance.services import generate_numero_facture_vente, calculate_tva, get_taux_tva_defaut
    from config_app.models import TypeFactureVente, LigneBudgetaire

    try:
        type_facture = TypeFactureVente.objects.get(pk=request.POST.get('type_facture'))
        taux_tva = to_decimal(request.POST.get('taux_tva', '20'))
        montant_ttc = abs(operation.credit)
        
        calcul = calculate_tva(montant_ttc, taux_tva)
        taux_mixte = request.POST.get('taux_mixte') == 'on'

        if taux_mixte:
            montant_ht = abs(to_decimal(request.POST.get('montant_ht'), default=str(calcul['ht'])))
            montant_tva = abs(to_decimal(request.POST.get('montant_tva'), default=str(calcul['tva'])))
        else:
            montant_ht = abs(calcul['ht'])
            montant_tva = abs(calcul['tva'])

        ligne_bud_pk = request.POST.get('ligne_budgetaire')
        etude_pk = request.POST.get('etude')

        from finance.models import Etude
        from datetime import datetime

        date_envoi_raw = request.POST.get('date_envoi', '')
        date_envoi = datetime.strptime(date_envoi_raw, '%Y-%m-%d').date() if date_envoi_raw else None

        numero = generate_numero_facture_vente(
            type_facture,
            operation.date_operation.year,
            operation.date_operation.month,
            suffixe=type_facture.suffixe,
        )

        fv = FactureVente.objects.create(
            operation=operation,
            type_facture=type_facture,
            numero=numero,
            etude=Etude.objects.get(pk=etude_pk) if etude_pk else None,
            libelle=request.POST.get('libelle', operation.info_complementaire),
            lien_drive=request.POST.get('lien_drive', ''),
            date_operation=operation.date_operation,
            date_envoi=date_envoi,
            taux_tva=taux_tva,
            taux_mixte=taux_mixte,
            montant_ttc=montant_ttc,
            montant_ht=montant_ht,
            montant_tva=montant_tva,
            ligne_budgetaire=LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None,
            pays_tva=request.POST.get('pays_tva', 'FR'),
            commentaire=request.POST.get('commentaire', ''),
        )

        operation.statut = 'processed'
        operation.save()
        messages.success(request, f"Facture de vente {fv.numero} créée avec succès.")
        
        # Choix de redirection
        to_next = 'save_next' in request.POST
        return _redirect_next(operation, to_next=to_next)

    except Exception as e:
        messages.error(request, f"Erreur lors de la création de la facture : {e}")
        return redirect('operations:process_operation', operation_id=operation.pk)


def _process_bv(request, operation):
    """Traite une opération débit en Bulletin de Versement."""
    from finance.models import BulletinVersement, Etude
    from finance.services import generate_numero_bv, calculate_cotisations_urssaf
    from config_app.models import ParametreCotisation
    from decimal import Decimal
    from datetime import datetime

    try:
        type_cotisant = request.POST.get('type_cotisant', 'etudiant')
        nb_jeh = abs(to_decimal(request.POST.get('nb_jeh', '0')))
        retrib = abs(to_decimal(request.POST.get('retribution_brute_par_jeh', '0')))

        try:
            params = ParametreCotisation.objects.get(type_cotisant=type_cotisant)
        except ParametreCotisation.DoesNotExist:
            params = None

        cotis = calculate_cotisations_urssaf(nb_jeh, type_cotisant, params)

        numero_propose = request.POST.get('numero') or generate_numero_bv(operation.date_operation.year)

        if BulletinVersement.objects.filter(numero=numero_propose).exists():
            messages.error(request, f"Le numéro BV {numero_propose} existe déjà.")
            return redirect('operations:process_operation', operation_id=operation.pk)

        date_emission_raw = request.POST.get('date_emission', '')
        date_emission = datetime.strptime(date_emission_raw, '%Y-%m-%d').date() if date_emission_raw else None

        etude_pk = request.POST.get('etude')

        bv = BulletinVersement.objects.create(
            operation=operation,
            numero=numero_propose,
            etude=Etude.objects.get(pk=etude_pk) if etude_pk else None,
            date_operation=operation.date_operation,
            date_emission=date_emission,
            reference_virement=request.POST.get('reference_virement', operation.reference),
            intervenant_nom=request.POST.get('intervenant_nom', ''),
            intervenant_prenom=request.POST.get('intervenant_prenom', ''),
            nb_jeh=nb_jeh,
            retribution_brute_par_jeh=retrib,
            taux=request.POST.get('taux', 'A'),
            type_cotisant=type_cotisant,
            assiette=cotis['assiette'],
            cotis_assurance_maladie=cotis['assurance_maladie'],
            cotis_accident_travail=cotis['accident_travail'],
            cotis_vieillesse_plafonnee=cotis['vieillesse_plafonnee'],
            cotis_vieillesse_deplafonnee=cotis['vieillesse_deplafonnee'],
            cotis_allocations_familiales=cotis['allocations_familiales'],
            cotis_csg_deductible=cotis['csg_deductible'],
            cotis_csg_non_deductible=cotis['csg_non_deductible'],
            total_cotisations_junior=cotis['total_junior'],
            total_cotisations_etudiant=cotis['total_etudiant'],
            commentaire=request.POST.get('commentaire', ''),
        )

        operation.statut = 'processed'
        operation.save()
        messages.success(request, f"Bulletin de versement {bv.numero} créé avec succès.")
        
        # Choix de redirection
        to_next = 'save_next' in request.POST
        return _redirect_next(operation, to_next=to_next)

    except Exception as e:
        messages.error(request, f"Erreur lors de la création du BV : {e}")
        return redirect('operations:process_operation', operation_id=operation.pk)


def _process_achat(request, operation):
    """Traite une opération débit en Facture d'achat."""
    from finance.models import FactureAchat
    from finance.services import generate_numero_facture_achat, calculate_tva
    from config_app.models import TypeAchat, LigneBudgetaire
    from decimal import Decimal
    from datetime import datetime

    try:
        type_achat = TypeAchat.objects.get(pk=request.POST.get('type_achat'))
        taux_tva = to_decimal(request.POST.get('taux_tva', '20'))
        montant_ttc = abs(operation.debit)
        taux_compose = request.POST.get('taux_compose') == 'on'

        if taux_compose:
            montant_ht = abs(to_decimal(request.POST.get('montant_ht'), default='0'))
            montant_tva = abs(to_decimal(request.POST.get('montant_tva'), default='0'))
        else:
            calcul = calculate_tva(montant_ttc, taux_tva)
            montant_ht = abs(calcul['ht'])
            montant_tva = abs(calcul['tva'])

        ligne_bud_pk = request.POST.get('ligne_budgetaire')
        date_reception_raw = request.POST.get('date_reception', '')
        date_reception = datetime.strptime(date_reception_raw, '%Y-%m-%d').date() if date_reception_raw else None

        numero = generate_numero_facture_achat(
            type_achat,
            operation.date_operation.year,
            operation.date_operation.month,
        )

        fa = FactureAchat(
            operation=operation,
            type_achat=type_achat,
            numero=numero,
            fournisseur=request.POST.get('fournisseur', ''),
            libelle=request.POST.get('libelle', operation.info_complementaire),
            lien_drive=request.POST.get('lien_drive', ''),
            date_operation=operation.date_operation,
            date_reception=date_reception,
            categorisation=request.POST.get('categorisation', 'service'),
            taux_tva=taux_tva,
            taux_compose=taux_compose,
            pays_tva=request.POST.get('pays_tva', 'FR'),
            montant_ttc=montant_ttc,
            montant_ht=montant_ht,
            montant_tva=montant_tva,
            ligne_budgetaire=LigneBudgetaire.objects.get(pk=ligne_bud_pk) if ligne_bud_pk else None,
            commentaire=request.POST.get('commentaire', ''),
        )
        fa.save()  # save() gère l'immobilisation automatique

        operation.statut = 'processed'
        operation.save()
        messages.success(request, f"Facture d'achat {fa.numero} créée avec succès.")
        
        # Choix de redirection
        to_next = 'save_next' in request.POST
        return _redirect_next(operation, to_next=to_next)

    except Exception as e:
        messages.error(request, f"Erreur lors de la création de la facture d'achat : {e}")
        return redirect('operations:process_operation', operation_id=operation.pk)


def operation_ignore(request, operation_id):
    """Marque rapidement une opération comme ignorée (HTMX)."""
    operation = get_object_or_404(Operation, pk=operation_id)
    if request.method == 'POST':
        operation.statut = 'ignored'
        operation.commentaire_ignoree = request.POST.get('commentaire', '')
        operation.save()
        messages.success(request, f"Opération ignorée.")
    return redirect('operations:process_list')


def operation_delete(request, pk):
    """Supprime manuellement une opération (pour tests)."""
    operation = get_object_or_404(Operation, pk=pk)
    libelle = operation.libelle
    operation.delete()
    messages.success(request, f"Opération « {libelle} » supprimée avec succès.")
    
    # Redirection intelligente
    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('operations:process_list')
