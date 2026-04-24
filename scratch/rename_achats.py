import os
import sys
import django
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flower_treso.settings')
django.setup()

from finance.models import FactureAchat
from config_app.models import TypeAchat

def rename_achats():
    # Sort by date
    achats = FactureAchat.objects.all().order_by('date_operation', 'id')
    
    counters = {}
    planned_names = {}
    
    print("Démarrage du renommage des factures d'achat (Etape 1 : temporaire)...")
    
    for fa in achats:
        # Use date_reception if present, else date_operation
        ref_date = fa.date_reception if fa.date_reception else fa.date_operation
        year_str = ref_date.strftime('%y')
        month_str = ref_date.strftime('%m')
        
        # Shared counter per month
        key = (year_str, month_str)
        counters[key] = counters.get(key, 0) + 1
        count = counters[key]
        
        # Prefix
        prefix = 'NF' if (fa.type_achat and fa.type_achat.suffixe == 'NF') else 'A'
        
        planned_names[fa.id] = f"{prefix}{year_str}{month_str}{count:02d}"
        
        # Temp rename
        fa.numero = f"TEMP_A_{fa.id}_{planned_names[fa.id]}"
        fa.save()
        
    print("Etape 2 : Application de la nomenclature...")
    for fa in achats:
        fa.numero = planned_names[fa.id]
        fa.save()
        print(f"ID {fa.id} -> {fa.numero}")

    print(f"\nTerminé. {len(achats)} factures d'achat traitées.")

if __name__ == "__main__":
    rename_achats()
