"""
Context processors pour Flower-Tréso.
Injecte les variables globales dans tous les templates.
"""
from operations.models import Operation


def global_context(request):
    """Variables disponibles dans tous les templates."""
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
        
        filtre_mois = list(set(processed_mois))
        request.session['filtre_mois'] = filtre_mois
    else:
        filtre_mois = request.session.get('filtre_mois', [])

    # Type de filtre date (operation vs facture)
    if 'date_filter_type' in request.GET:
        date_filter_type = request.GET.get('date_filter_type')
        request.session['date_filter_type'] = date_filter_type
    else:
        date_filter_type = request.session.get('date_filter_type', 'operation')

    # Gestion de l'année (Multi-sélection)
    if 'annee' in request.GET:
        annee_raw = request.GET.getlist('annee')
        filtre_annee = [a for a in annee_raw if a]
        request.session['filtre_annee'] = filtre_annee
    else:
        filtre_annee = request.session.get('filtre_annee', ['2025'])
        if isinstance(filtre_annee, str):
            filtre_annee = [filtre_annee] if filtre_annee else ['2025']

    # Opérations en attente pour le badge sidebar
    try:
        pending_count = Operation.objects.filter(statut='pending').count()
    except Exception:
        pending_count = 0

    months_list = [
        ('1', 'Janvier'), ('2', 'Février'), ('3', 'Mars'), ('4', 'Avril'),
        ('5', 'Mai'), ('6', 'Juin'), ('7', 'Juillet'), ('8', 'Août'),
        ('9', 'Septembre'), ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Décembre')
    ]

    available_years = [2023, 2024, 2025, 2026]

    return {
        'filtre_mois': filtre_mois,
        'filtre_annee': filtre_annee,
        'date_filter_type': date_filter_type,
        'pending_count': pending_count,
        'months_list': months_list,
        'available_years': available_years,
    }
