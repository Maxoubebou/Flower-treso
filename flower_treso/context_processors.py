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

    # Gestion de l'année
    if 'annee' in request.GET:
        filtre_annee = request.GET.get('annee')
        request.session['filtre_annee'] = filtre_annee
    else:
        filtre_annee = request.session.get('filtre_annee', '2025')

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

    return {
        'filtre_mois': filtre_mois,
        'filtre_annee': filtre_annee,
        'pending_count': pending_count,
        'months_list': months_list,
    }
