import os
import sys
import django

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flower_treso.settings')
django.setup()

from finance.models import FactureVente
from config_app.models import TypeFactureVente

print("Types de factures existants :")
for tf in TypeFactureVente.objects.all():
    print(f"ID: {tf.id}, Nom: {tf.nom}, Suffixe model: {tf.suffixe}, Est sub: {tf.est_subvention}")

print("\nQuelques factures de ventes :")
for fv in FactureVente.objects.all().order_by('-date_operation')[:10]:
    print(f"Ref: {fv.numero}, Date: {fv.date_operation}, Type: {fv.type_facture.nom if fv.type_facture else 'Aucun'}")
