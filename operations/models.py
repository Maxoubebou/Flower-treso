from django.db import models


class ImportBatch(models.Model):
    """Regroupement d'un import CSV."""
    created_at = models.DateTimeField(auto_now_add=True)
    filename = models.CharField(max_length=255)
    nb_rows = models.IntegerField(default=0)

    class Meta:
        verbose_name = "Import CSV"
        verbose_name_plural = "Imports CSV"
        ordering = ['-created_at']

    def __str__(self):
        return f"Import {self.filename} ({self.created_at:%d/%m/%Y})"


class Operation(models.Model):
    """
    Ligne brute issue du fichier CSV bancaire.
    Statuts : pending → traitement en attente, processed → traitée, ignored → ignorée (virement interne).
    """
    STATUT_CHOICES = [
        ('pending', 'En attente'),
        ('processed', 'Traitée'),
        ('ignored', 'Ignorée'),
    ]
    TYPE_OPERATION_CHOICES = [
        ('credit', 'Crédit'),
        ('debit', 'Débit'),
    ]

    # Colonnes CSV
    libelle = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    info_complementaire = models.TextField(blank=True)
    type_operation = models.CharField(max_length=10, choices=TYPE_OPERATION_CHOICES)
    debit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    credit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    date_operation = models.DateField()
    date_valeur = models.DateField(null=True, blank=True)
    pointage = models.CharField(max_length=50, blank=True)

    # Métadonnées de traitement
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='pending')
    commentaire_ignoree = models.TextField(blank=True, help_text="Commentaire pour virement interne ignoré")
    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.CASCADE, related_name='operations',
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_operation', '-id']
        verbose_name = "Opération"
        verbose_name_plural = "Opérations"

    def __str__(self):
        montant = self.credit if self.credit else f"-{self.debit}"
        return f"{self.date_operation} | {self.libelle} | {montant}€"

    @property
    def montant(self):
        if self.credit:
            return self.credit
        return -self.debit if self.debit else None

    @property
    def est_credit(self):
        return self.type_operation == 'credit'

    @property
    def est_debit(self):
        return self.type_operation == 'debit'
