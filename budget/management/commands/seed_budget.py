from django.core.management.base import BaseCommand
from budget.models import BudgetSubCategory, BudgetItem
from config_app.models import LigneBudgetaire

class Command(BaseCommand):
    help = "Seed the complete budget structure from the treasury reference."

    def handle(self, *args, **options):
        # Helper to get or create LigneBudgetaire
        def get_lb(name):
            lb, _ = LigneBudgetaire.objects.get_or_create(nom=name)
            return lb

        # Clear existing budget structure to avoid duplicates/conflicts during re-seed
        BudgetItem.objects.all().delete()
        BudgetSubCategory.objects.all().delete()

        # ─── PRODUITS ──────────────────────────────────────────
        p_root = {
            'COTISATIONS': ['Cotisations (adhérents de la Junior)'],
            'SUBVENTIONS': ['Subventions INSA', 'Partenariat Neutron IT'],
            'PRODUITS FINANCIERS': ['Intérêt sur livret/compte épargne'],
            'AUTRES': [
                'Refacturation softshell/polos/sweats',
                'Refacturation CRA aux étudiants',
                'Refacturation CNH aux étudiants',
                'Refacturation CRP aux étudiants',
                'Refacturation CNE aux étudiants',
                'Refacturation SOI aux membres'
            ],
            'ÉTUDES': ['Prestation JEH']
        }

        for cat_name, items in p_root.items():
            cat = BudgetSubCategory.objects.create(name=cat_name, group='produit')
            for i, item_name in enumerate(items):
                BudgetItem.objects.create(subcategory=cat, ligne_budgetaire=get_lb(item_name), ordre=i*10)

        # ─── CHARGES ───────────────────────────────────────────
        # Charges root level
        c_variables = BudgetSubCategory.objects.create(name='Charges Variables', group='charge', ordre=10)
        c_fixes = BudgetSubCategory.objects.create(name='Charges Fixes', group='charge', ordre=20)

        # Variables Sub-levels
        struct_vars = {
            'RETRIBUTIONS DES INTERVENANTS': ['Rétributions brutes', 'Cotisations URSSAF (part junior)'],
            'FRAIS DE GESTION QUOTIDIENNE (VAR)': ['Reprographie', 'Frais postaux (+voeux)']
        }
        for cat_name, items in struct_vars.items():
            sub = BudgetSubCategory.objects.create(name=cat_name, group='charge', parent=c_variables)
            for i, item_name in enumerate(items):
                BudgetItem.objects.create(subcategory=sub, ligne_budgetaire=get_lb(item_name), ordre=i*10)

        # Fixes Sub-levels
        struct_fixes = {
            'FRAIS DE STRUCTURE': [
                'Expert-comptable', 'Frais bancaires', 'CFE', 'Assurance MAIF', 
                'Abonnement internet', 'Logiciel comptable'
            ],
            'FRAIS DE GESTION QUOTIDIENNE (FIXE)': [
                'Fournitures non consommables', 'Fournitures consommables'
            ],
            'CNJE': [
                'Cotisation CNJE', 
                'Déplacements et nuit AGP (fixe, une personne)',
                'Déplacements et nuit AGP (une personne suppl)',
                'Places AGP (fixe, une personne)',
                'Places AGP (une personne supplémentaire)',
                'Frais d\'audit CNJE Décembre 2025',
                'Frais d\'audit CNJE mi mandat'
            ],
            'CONGRÈS CNJE': [
                'Places CRA', 'Déplacements CRA', 'Places CNH', 'Déplacements CNH',
                'Places CRP', 'Déplacements CRP', 'Places CNE', 'Déplacements CNE'
            ],
            'PÔLE COMMERCIAL': [
                'RDV clients', 'Frais postaux (Pôle)', 'Cartes de visite', 
                'Outils de prospection', 'Team building du pôle'
            ],
            'PÔLE AFFAIRE': ['Refacturation des frais d\'étude'],
            'PÔLE SYSTÈME D\'INFORMATION': [
                'Serveurs', 'Noms de domaine', 'Crédits logiciel signature electronique',
                'Canva', 'ERP (Beequick, SIAJE..)', 'Google Suite'
            ],
            'PÔLE COMMUNICATION': [
                'Frais lié à une conférence donné par un membre', 'Conférence',
                'Evènement JER', 'Polos / softshells', 'Appareil photo/caméra'
            ],
            'PÔLE QUALITE': [
                'Certification (ISO 9001)', 'Frais d\'audit certification (nourriture...)'
            ],
            'PÔLE RH': [
                'Évènement pour le campus (appel à projet, don)', 'Recrutement (Évènements)',
                'Resto bureau', 'Resto mandat', 'Bouffe building', 'Team building',
                'WOIJOI', 'Nourriture pour longue réu', 'Raclette de formation', 'SOI',
                'Frais formations (Ateliers/Week-end) Hors-RFP'
            ],
            'DOTATIONS ET PROVISIONS': [
                'Dotation aux amortissements', 'Provisions pour clients douteux'
            ]
        }

        for cat_name, items in struct_fixes.items():
            sub = BudgetSubCategory.objects.create(name=cat_name, group='charge', parent=c_fixes)
            for i, item_name in enumerate(items):
                BudgetItem.objects.create(subcategory=sub, ligne_budgetaire=get_lb(item_name), ordre=i*10)

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {BudgetItem.objects.count()} budget items."))
