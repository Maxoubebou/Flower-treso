import os
from django import template

register = template.Library()

@register.filter
def sum_ttc(lignes):
    """Calcule la somme des TTC d'une liste de lignes NDF."""
    return sum(l.montant_ttc for l in lignes)

@register.filter
def get_file_extension(value):
    """Retourne l'extension d'un fichier en minuscules."""
    name, extension = os.path.splitext(value.name)
    return extension.lower()

@register.filter
def is_pdf(value):
    """Vérifie si le fichier est un PDF."""
    return get_file_extension(value) == '.pdf'

@register.filter
def is_image(value):
    """Vérifie si le fichier est une image."""
    return get_file_extension(value) in ['.jpg', '.jpeg', '.png', '.gif', '.webp']

@register.filter
def days_since(value):
    """Retourne le nombre de jours entre maintenant et la valeur."""
    from django.utils import timezone
    if not value: return ""
    diff = timezone.now() - value
    return diff.days
