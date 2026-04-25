from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import ValidationError
from django.contrib import messages

class DomainRestrictionAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Vérifie que l'adresse email se termine par @ouest-insa.fr
        """
        email = sociallogin.user.email
        if not email.endswith('@ouest-insa.fr'):
            messages.error(request, f"Accès refusé. L'adresse {email} n'appartient pas au domaine @ouest-insa.fr.")
            raise ValidationError("Accès réservé aux membres @ouest-insa.fr")
