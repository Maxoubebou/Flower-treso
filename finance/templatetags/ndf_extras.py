from django import template

register = template.Library()

@register.filter
def sum_ttc(lignes):
    """Calcule la somme des TTC d'une liste de lignes NDF."""
    return sum(l.montant_ttc for l in lignes)
