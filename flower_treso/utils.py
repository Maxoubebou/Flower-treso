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


def evaluate_budget_formula(formula, context, default=Decimal('0')):
    """
    Évalue une formule de budget avec substitution de variables.
    Ex: formula="0.2 * [Salaires] + 100", context={"Salaires": 1000}
    """
    if not formula:
        return default

    # 1. On nettoie la formule (enlever le = initial si présent)
    clean_formula = str(formula).strip().lstrip('=')

    # 2. On substitue les variables [Nom de ligne] ou les IDs (ex: ET1)
    # On commence par les crochets [...] qui sont explicites
    bracket_matches = re.findall(r'\[(.*?)\]', clean_formula)
    for match in sorted(set(bracket_matches), key=len, reverse=True):
        val = context.get(match, 0)
        clean_formula = clean_formula.replace(f'[{match}]', f'({val})')

    # Ensuite on cherche les IDs "nus" (ex: ET1, SA2)
    # Pattern: 2+ lettres majuscules suivies de chiffres, isolés par des limites de mots
    naked_matches = re.findall(r'\b([A-Z]{2,}\d+)\b', clean_formula)
    for match in sorted(set(naked_matches), key=len, reverse=True):
        if match in context:
            val = context.get(match, 0)
            # On utilise une substitution par regex pour respecter les \b
            clean_formula = re.sub(rf'\b{match}\b', f'({val})', clean_formula)

    # 3. Sécurité : on n'accepte que des caractères sûrs pour eval
    # Chiffres, opérateurs, parenthèses, point, virgule, espace
    clean_formula = clean_formula.replace(',', '.')
    if re.fullmatch(r'[0-9+\-*/().\s]+', clean_formula):
        try:
            # Env totalement vide pour la sécurité
            result = eval(clean_formula, {"__builtins__": {}}, {})
            return Decimal(str(result))
        except Exception:
            return default
    else:
        # Si caractères louches, on retourne le défaut
        return default
