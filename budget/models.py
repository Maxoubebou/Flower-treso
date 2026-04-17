from django.db import models
from config_app.models import LigneBudgetaire

class BudgetSubCategory(models.Model):
    GROUP_CHOICES = [
        ('produit', 'Produits'),
        ('charge', 'Charges'),
    ]
    name = models.CharField(max_length=100)
    group = models.CharField(max_length=10, choices=GROUP_CHOICES)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['group', 'ordre', 'name']
        verbose_name = "Sous-catégorie de budget"
        verbose_name_plural = "Sous-catégories de budget"

    def __str__(self):
        return f"[{self.get_group_display()}] {self.name}"


class BudgetItem(models.Model):
    subcategory = models.ForeignKey(BudgetSubCategory, on_delete=models.CASCADE, related_name='items')
    ligne_budgetaire = models.ForeignKey(LigneBudgetaire, on_delete=models.CASCADE, related_name='budget_items')
    
    # Scénarios (Valeurs HT)
    scenario_bas = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    scenario_moyen = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    scenario_haut = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    ordre = models.PositiveIntegerField(default=0)
    commentaire = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['ordre', 'ligne_budgetaire__nom']
        verbose_name = "Ligne de budget calculée"
        verbose_name_plural = "Lignes de budget calculées"

    def __str__(self):
        return f"{self.subcategory.name} — {self.ligne_budgetaire.nom}"
