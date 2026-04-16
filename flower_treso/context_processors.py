"""
Context processors pour Flower-Tréso.
Injecte les variables globales dans tous les templates.
"""
from operations.models import Operation


def global_context(request):
    """Variables disponibles dans tous les templates."""
    # Filtre mois/année persistant via sessions
    filtre_mois = request.GET.get('mois') or request.session.get('filtre_mois', '')
    filtre_annee = request.GET.get('annee') or request.session.get('filtre_annee', '')

    if request.GET.get('mois'):
        request.session['filtre_mois'] = filtre_mois
    if request.GET.get('annee'):
        request.session['filtre_annee'] = filtre_annee

    # Opérations en attente pour le badge sidebar
    try:
        pending_count = Operation.objects.filter(statut='pending').count()
    except Exception:
        pending_count = 0

    return {
        'filtre_mois': str(filtre_mois) if filtre_mois else '',
        'filtre_annee': str(filtre_annee) if filtre_annee else '',
        'pending_count': pending_count,
    }
