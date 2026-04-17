from decimal import Decimal, InvalidOperation
import re

def to_decimal(value, default='0'):
    """
    Nettoie et convertit une chaîne en Decimal.
    Gère les virgules, les espaces, les formats invalides et les formules (+, -, *, /).
    Ex: "=200+100*2", "1000+500", "3*450"
    """
    if value is None or value == '':
        return Decimal(default)
    
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))

    clean_val = str(value).strip().lstrip('=')   # accepte "=200+100" ou "200+100"
    
    # Si c'est une expression (contient des opérateurs), on évalue
    if re.search(r'[+\-*/]', clean_val):
        # Sécurité : on n'accepte que des chiffres, opérateurs, parenthèses, point, virgule, espace
        if re.fullmatch(r'[0-9+\-*/().,\s]+', clean_val):
            try:
                clean_val = clean_val.replace(',', '.')
                result = eval(clean_val, {"__builtins__": {}}, {})  # env totalement vide
                return Decimal(str(result))
            except Exception:
                return Decimal(default)
        else:
            return Decimal(default)
    
    # Nettoyage simple pour un nombre pur
    clean_val = clean_val.replace(' ', '').replace('\xa0', '').replace(',', '.')
    
    try:
        return Decimal(clean_val)
    except (InvalidOperation, ValueError):
        return Decimal(default)
