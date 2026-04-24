import os
import sys
import django
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flower_treso.settings')
django.setup()

from finance.models import FactureVente
from config_app.models import TypeFactureVente

def rename_invoices():
    # Sort all invoices by date then order within the same date
    # We use date_operation (or date_envoi) for chronolgy
    # Since date_envoi can be null, we coalesce in sorting or use operation
    invoices = FactureVente.objects.all().order_by('date_operation', 'id')
    
    # Counters per (Prefix, Year, Month)
    counters = {}
    
    # Mapping for suffixes as requested
    # _A for accompte, _S for solde, _C for cotisations, empty for subventions, _REF for refac
    suffix_map = {
        'A': '_A',
        'S': '_S',
        'C': '_C',
        'SU': '', 
        'R': '_REF',
        'AV': '_AV'
    }
    
    print("Démarrage du renommage des factures de vente (Etape 1 : renommage temporaire)...")
    
    # Store the intended names
    planned_names = {}
    for fv in invoices:
        ref_date = fv.date_envoi if fv.date_envoi else fv.date_operation
        year_str = ref_date.strftime('%y')
        month_str = ref_date.strftime('%m')
        prefix = 'S' if fv.type_facture.est_subvention else 'FV'
        key = (prefix, year_str, month_str)
        counters[key] = counters.get(key, 0) + 1
        count = counters[key]
        
        s_code = fv.type_facture.suffixe
        suffix = suffix_map.get(s_code, f"_{s_code}")
        planned_names[fv.id] = f"{prefix}{year_str}{month_str}{count:02d}{suffix}"
        
        # Pass 1: Temporary name to free up names
        fv.numero = f"TEMP_{fv.id}_{planned_names[fv.id]}"
        fv.save()
        
    print("Etape 2 : Application de la nouvelle nomenclature...")
    total_renamed = 0
    for fv in invoices:
        final_ref = planned_names[fv.id]
        fv.numero = final_ref
        fv.save()
        total_renamed += 1
            
    print(f"\nTerminé. {total_renamed} factures ont été traitées.")
            
    print(f"\nTerminé. {total_renamed} factures ont été renommées.")

if __name__ == "__main__":
    rename_invoices()
