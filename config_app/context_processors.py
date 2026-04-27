
from config_app.models import UserPoste, PostePermission

def rbac_permissions(request):
    """Injecte les permissions du poste de l'utilisateur dans le contexte global."""
    if not request.user.is_authenticated:
        return {}

    # Initialisation des droits par défaut (tout à False)
    perms = {
        'can_access_ventes': False,
        'can_access_achats': False,
        'can_access_operations': False,
        'can_access_ndf_admin': False,
        'can_access_etudes': False,
        'can_access_budget': False,
        'can_access_settings': False,
        'dashboard_show_kpi_global': False,
        'dashboard_show_kpi_ndf_admin': False,
        'dashboard_show_personal_ndf': True,  # Par défaut actif
        'dashboard_show_tva_urssaf': False,
        'is_maxime': False
    }

    # Cas particulier Maxime
    if request.user.email == "maxime.even@ouest-insa.fr":
        for k in perms: perms[k] = True
        perms['is_maxime'] = True
        return {'user_perms': perms}

    # Récupération du Poste
    try:
        up = UserPoste.objects.select_related('poste').get(email=request.user.email)
        poste = up.poste
    except UserPoste.DoesNotExist:
        poste = PostePermission.objects.filter(is_default=True).first()

    if poste:
        perms['can_access_ventes'] = poste.can_access_ventes
        perms['can_access_achats'] = poste.can_access_achats
        perms['can_access_operations'] = poste.can_access_operations
        perms['can_access_ndf_admin'] = poste.can_access_ndf_admin
        perms['can_access_etudes'] = poste.can_access_etudes
        perms['can_access_budget'] = poste.can_access_budget
        perms['can_access_settings'] = poste.can_access_settings
        perms['dashboard_show_kpi_global'] = poste.dashboard_show_kpi_global
        perms['dashboard_show_kpi_ndf_admin'] = poste.dashboard_show_kpi_ndf_admin
        perms['dashboard_show_personal_ndf'] = poste.dashboard_show_personal_ndf
        perms['dashboard_show_tva_urssaf'] = poste.dashboard_show_tva_urssaf
    
    # Si SuperUser Django, on donne tout
    if request.user.is_superuser:
        for k in perms: perms[k] = True

    return {'user_perms': perms}
