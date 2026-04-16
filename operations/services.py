"""
operations/services.py
Logique de parsing CSV et gestion des numéros chronologiques.
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from datetime import datetime

from .models import Operation, ImportBatch


# Colonnes attendues dans le CSV (insensible à la casse / espaces)
CSV_COLUMNS = [
    'libelle',
    'reference',
    'info_complementaire',
    'type_operation',
    'debit',
    'credit',
    'date_operation',
    'date_valeur',
    'pointage',
]

CSV_COLUMN_ALIASES = {
    'libellé simplifié': 'libelle',
    'libelle simplifie': 'libelle',
    'libelle': 'libelle',
    'référence': 'reference',
    'reference': 'reference',
    'informations complémentaires': 'info_complementaire',
    'informations complementaires': 'info_complementaire',
    'info_complementaire': 'info_complementaire',
    'type opération': 'type_operation',
    'type operation': 'type_operation',
    'type_operation': 'type_operation',
    'débit': 'debit',
    'debit': 'debit',
    'crédit': 'credit',
    'credit': 'credit',
    'date opération': 'date_operation',
    'date operation': 'date_operation',
    'date_operation': 'date_operation',
    'date de valeur': 'date_valeur',
    'date_valeur': 'date_valeur',
    'pointage': 'pointage',
}

DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y']


def _parse_date(value: str):
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Format de date non reconnu : {value!r}")


def _parse_decimal(value: str):
    if not value or not value.strip():
        return None
    value = value.strip().replace(' ', '').replace(',', '.')
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_csv(file_content: bytes, filename: str = 'import.csv') -> tuple[ImportBatch, list[Operation], list[str]]:
    """
    Parse le contenu binaire d'un fichier CSV et crée les opérations en base.

    Returns:
        (batch, operations_créées, erreurs_ligne)
    """
    errors = []
    operations = []

    # Détecter l'encodage (UTF-8 ou latin-1)
    try:
        text = file_content.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = file_content.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    if reader.fieldnames is None:
        # Essai avec virgule
        reader = csv.DictReader(io.StringIO(text), delimiter=',')

    # Normaliser les noms de colonnes
    normalized_fields = {}
    if reader.fieldnames:
        for col in reader.fieldnames:
            key = col.strip().lower()
            if key in CSV_COLUMN_ALIASES:
                normalized_fields[col] = CSV_COLUMN_ALIASES[key]

    batch = ImportBatch.objects.create(filename=filename)

    rows = list(reader)
    batch.nb_rows = len(rows)
    batch.save()

    for i, row in enumerate(rows, start=2):
        # Normaliser les clés
        normalized_row = {normalized_fields.get(k, k.strip().lower()): v for k, v in row.items()}

        try:
            date_op = _parse_date(normalized_row.get('date_operation', ''))
        except ValueError as e:
            errors.append(f"Ligne {i}: {e}")
            continue

        debit = _parse_decimal(normalized_row.get('debit', ''))
        credit = _parse_decimal(normalized_row.get('credit', ''))

        if debit and debit > 0:
            type_op = 'debit'
        elif credit and credit > 0:
            type_op = 'credit'
        else:
            # Chercher dans la colonne type_operation
            type_raw = normalized_row.get('type_operation', '').strip().lower()
            type_op = 'credit' if 'cr' in type_raw else 'debit'

        date_valeur_raw = normalized_row.get('date_valeur', '')
        try:
            date_valeur = _parse_date(date_valeur_raw) if date_valeur_raw.strip() else None
        except ValueError:
            date_valeur = None

        op = Operation(
            libelle=normalized_row.get('libelle', '').strip(),
            reference=normalized_row.get('reference', '').strip(),
            info_complementaire=normalized_row.get('info_complementaire', '').strip(),
            type_operation=type_op,
            debit=debit,
            credit=credit,
            date_operation=date_op,
            date_valeur=date_valeur,
            pointage=normalized_row.get('pointage', '').strip(),
            import_batch=batch,
            statut='pending',
        )
        operations.append(op)

    if operations:
        Operation.objects.bulk_create(operations)

    return batch, operations, errors


def get_next_chrono(annee: int, mois: int, prefix: str = 'FV') -> int:
    """
    Retourne le prochain numéro chronologique du mois pour le préfixe donné.
    Utilisé pour la nomenclature automatique des factures.
    """
    from finance.models import FactureVente, FactureAchat, BulletinVersement

    periode = f"{annee}{mois:02d}"

    if prefix in ('FV', 'S'):
        from finance.models import FactureVente
        count = FactureVente.objects.filter(
            date_operation__year=annee,
            date_operation__month=mois
        ).count()
    elif prefix == 'FA':
        count = FactureAchat.objects.filter(
            date_operation__year=annee,
            date_operation__month=mois
        ).count()
    elif prefix == 'BV':
        count = BulletinVersement.objects.filter(
            date_operation__year=annee
        ).count()
    else:
        count = 0

    return count + 1
