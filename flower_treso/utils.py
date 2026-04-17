from decimal import Decimal, ConversionSyntax
import re

def to_decimal(value, default='0'):
    """
    Nettoie et convertit une chaîne en Decimal.
    Gère les virgules, les espaces et les formats invalides.
    """
    if value is None or value == '':
        return Decimal(default)
    
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))

    # Nettoyage : retirer tout sauf chiffres, point, virgule et signe moins
    clean_val = str(value).replace(' ', '').replace('\xa0', '')
    clean_val = clean_val.replace(',', '.')
    
    try:
        return Decimal(clean_val)
    except (ConversionSyntax, ValueError):
        return Decimal(default)
