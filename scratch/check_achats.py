import os
import sys
import django

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flower_treso.settings')
django.setup()

from finance.models import FactureAchat
from config_app.models import TypeAchat

print("Types d'achats existants :")
for ta in TypeAchat.objects.all():
    print(f"ID: {ta.id}, Nom: {ta.nom}, Suffixe: {ta.suffixe}")

print("\nQuelques factures d'achat :")
for fa in FactureAchat.objects.all().order_by('-date_operation')[:10]:
    print(f"Ref: {fa.numero}, Date: {fa.date_operation}, Type: {fa.type_achat.nom if fa.type_achat else 'Aucun'}")
