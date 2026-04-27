
from django.shortcuts import redirect
from django.urls import resolve
from django.contrib import messages
from config_app.models import UserPoste, PostePermission

class RBACMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        # 1. Privilège Hardcodé pour Maxime
        if request.user.email == "maxime.even@ouest-insa.fr":
            return self.get_response(request)

        # 2. Récupération du Poste
        try:
            up = UserPoste.objects.select_related('poste').get(email=request.user.email)
            poste = up.poste
        except UserPoste.DoesNotExist:
            # Récupérer le poste par défaut
            poste = PostePermission.objects.filter(is_default=True).first()
            if not poste:
                # Si pas de poste par défaut, on laisse passer (Django Auth gérera)
                # Mais il vaut mieux être restrictif
                return self.get_response(request)

        # 3. Vérification de l'accès
        url_name = resolve(request.path_info).url_name
        app_name = resolve(request.path_info).app_name
        full_url = f"{app_name}:{url_name}" if app_name else url_name

        # Pages toujours autorisées
        public_pages = ['dashboard', 'logout', 'ndf_submit', 'ndf_download_pdf', 'login']
        if url_name in public_pages:
            return self.get_response(request)

        # Mapping des permissions
        access_denied = False
        
        # Settings (Strict)
        if app_name == 'config_app' or 'settings' in url_name:
            if not poste.can_access_settings:
                access_denied = True
        
        # Finance - Ventes
        elif 'ventes' in url_name or full_url in ['finance:vente_detail', 'finance:vente_edit']:
            if not poste.can_access_ventes:
                access_denied = True
        
        # Finance - Achats
        elif 'achat' in url_name and 'ndf' not in url_name:
            if not poste.can_access_achats:
                access_denied = True
                
        # Operations
        elif app_name == 'operations':
            if not poste.can_access_operations:
                access_denied = True
                
        # Admin NDF
        elif full_url in ['finance:ndf_manage', 'finance:ndf_validate', 'finance:ndf_reject', 'finance:ndf_history']:
            if not poste.can_access_ndf_admin:
                access_denied = True
                
        # Etudes
        elif 'etude' in url_name:
            if not poste.can_access_etudes:
                access_denied = True
                
        # Budget
        elif 'budget' in url_name:
            if not poste.can_access_budget:
                access_denied = True

        if access_denied:
            messages.error(request, "Vous n'avez pas les droits nécessaires pour accéder à cette page.")
            return redirect('reporting:dashboard')

        return self.get_response(request)
