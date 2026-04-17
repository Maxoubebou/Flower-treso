from django.db import models
from django.core.exceptions import ValidationError
from operations.models import Operation
from config_app.models import LigneBudgetaire, TypeFactureVente, TypeAchat


class Etude(models.Model):
    """Référence d'étude partagée (Achats / Ventes / BV)."""
    reference = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['reference']
        verbose_name = "Étude"
        verbose_name_plural = "Études"

    def __str__(self):
        return f"{self.reference} — {self.nom}"


class FactureVente(models.Model):
    """Facture de vente (crédit bancaire qualifié)."""
    PAYS_TVA_CHOICES = [
        ('FR', 'France'),
        ('intracom', 'Intracom UE'),
        ('extracom', 'Extra UE'),
    ]

    operation = models.OneToOneField(
        Operation, on_delete=models.CASCADE,
        related_name='facture_vente', null=True, blank=True
    )
    type_facture = models.ForeignKey(
        TypeFactureVente, on_delete=models.PROTECT, related_name='factures'
    )
    numero = models.CharField(max_length=30, unique=True, blank=True)
    etude = models.ForeignKey(
        Etude, on_delete=models.SET_NULL, null=True, blank=True, related_name='factures_vente'
    )
    libelle = models.CharField(max_length=255, blank=True)
    lien_drive = models.URLField(max_length=500, blank=True)
    date_operation = models.DateField()
    date_envoi = models.DateField(null=True, blank=True)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    taux_mixte = models.BooleanField(default=False)
    montant_ttc = models.DecimalField(max_digits=12, decimal_places=2)
    montant_ht = models.DecimalField(max_digits=12, decimal_places=2)
    montant_tva = models.DecimalField(max_digits=12, decimal_places=2)
    ligne_budgetaire = models.ForeignKey(
        LigneBudgetaire, on_delete=models.SET_NULL, null=True, blank=True
    )
    pays_tva = models.CharField(max_length=20, choices=PAYS_TVA_CHOICES, default='FR')
    commentaire = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_operation', '-numero']
        verbose_name = "Facture de vente"
        verbose_name_plural = "Factures de vente"

    def save(self, *args, **kwargs):
        # Force positive values
        if self.montant_ttc: self.montant_ttc = abs(self.montant_ttc)
        if self.montant_ht: self.montant_ht = abs(self.montant_ht)
        if self.montant_tva: self.montant_tva = abs(self.montant_tva)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.libelle} ({self.montant_ttc}€)"

    @property
    def annee(self):
        return self.date_operation.year

    @property
    def mois(self):
        return self.date_operation.month


class BulletinVersement(models.Model):
    """Bulletin de Versement (débit bancaire — paiement intervenant)."""
    TAUX_CHOICES = [
        ('A', 'Taux A'),
        ('B', 'Taux B'),
        ('C', 'Taux C'),
        ('D', 'Taux D'),
    ]
    TYPE_COTISANT_CHOICES = [
        ('junior', 'Junior-Entreprise'),
        ('etudiant', 'Étudiant'),
    ]

    operation = models.OneToOneField(
        Operation, on_delete=models.CASCADE,
        related_name='bulletin_versement', null=True, blank=True
    )
    numero = models.CharField(max_length=20, unique=True)
    etude = models.ForeignKey(
        Etude, on_delete=models.SET_NULL, null=True, blank=True, related_name='bulletins'
    )
    date_operation = models.DateField()
    date_emission = models.DateField(null=True, blank=True)
    reference_virement = models.CharField(max_length=100, blank=True)

    # Intervenant
    intervenant_nom = models.CharField(max_length=100)
    intervenant_prenom = models.CharField(max_length=100)
    nb_jeh = models.DecimalField(max_digits=6, decimal_places=2)
    retribution_brute_par_jeh = models.DecimalField(max_digits=8, decimal_places=2)
    taux = models.CharField(max_length=2, choices=TAUX_CHOICES, default='A')
    type_cotisant = models.CharField(max_length=20, choices=TYPE_COTISANT_CHOICES, default='etudiant')

    # Cotisations calculées (stockées pour reporting)
    assiette = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_assurance_maladie = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_accident_travail = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_vieillesse_plafonnee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_vieillesse_deplafonnee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_allocations_familiales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_csg_deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cotis_csg_non_deductible = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cotisations_junior = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cotisations_etudiant = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    commentaire = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_operation', '-numero']
        verbose_name = "Bulletin de versement"
        verbose_name_plural = "Bulletins de versement"

    def __str__(self):
        return f"{self.numero} — {self.intervenant_prenom} {self.intervenant_nom}"

    @property
    def retribution_brute_totale(self):
        return self.nb_jeh * self.retribution_brute_par_jeh

    def save(self, *args, **kwargs):
        # Force positive values
        if self.nb_jeh: self.nb_jeh = abs(self.nb_jeh)
        if self.retribution_brute_par_jeh: self.retribution_brute_par_jeh = abs(self.retribution_brute_par_jeh)
        if self.assiette: self.assiette = abs(self.assiette)
        if self.total_cotisations_junior: self.total_cotisations_junior = abs(self.total_cotisations_junior)
        if self.total_cotisations_etudiant: self.total_cotisations_etudiant = abs(self.total_cotisations_etudiant)
        super().save(*args, **kwargs)

    @property
    def total_cotisations(self):
        return self.total_cotisations_junior + self.total_cotisations_etudiant


class FactureAchat(models.Model):
    """Facture d'achat ou note de frais (débit bancaire)."""
    PAYS_TVA_CHOICES = [
        ('FR', 'France'),
        ('intracom', 'Intracom UE'),
        ('extracom', 'Extra UE'),
    ]
    CATEGORISATION_CHOICES = [
        ('service', 'Service'),
        ('bien', 'Bien'),
        ('immobilisation', 'Immobilisation'),
    ]

    operation = models.OneToOneField(
        Operation, on_delete=models.CASCADE,
        related_name='facture_achat', null=True, blank=True
    )
    type_achat = models.ForeignKey(
        TypeAchat, on_delete=models.PROTECT, related_name='factures'
    )
    numero = models.CharField(max_length=30, unique=True, blank=True)
    fournisseur = models.CharField(max_length=255)
    libelle = models.CharField(max_length=255, blank=True)
    lien_drive = models.URLField(max_length=500, blank=True)
    date_operation = models.DateField()
    date_reception = models.DateField(null=True, blank=True)
    categorisation = models.CharField(
        max_length=20, choices=CATEGORISATION_CHOICES, default='service'
    )
    immobilisation = models.BooleanField(
        default=False, help_text="Auto si Bien > 500€, non modifiable manuellement"
    )
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    taux_compose = models.BooleanField(default=False)
    pays_tva = models.CharField(max_length=20, choices=PAYS_TVA_CHOICES, default='FR')
    montant_ttc = models.DecimalField(max_digits=12, decimal_places=2)
    montant_ht = models.DecimalField(max_digits=12, decimal_places=2)
    montant_tva = models.DecimalField(max_digits=12, decimal_places=2)
    ligne_budgetaire = models.ForeignKey(
        LigneBudgetaire, on_delete=models.SET_NULL, null=True, blank=True
    )
    commentaire = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_operation', '-numero']
        verbose_name = "Facture d'achat"
        verbose_name_plural = "Factures d'achat"

    def __str__(self):
        return f"{self.numero} — {self.fournisseur} ({self.montant_ttc}€)"

    def save(self, *args, **kwargs):
        # Force positive values
        if self.montant_ttc: self.montant_ttc = abs(self.montant_ttc)
        if self.montant_ht: self.montant_ht = abs(self.montant_ht)
        if self.montant_tva: self.montant_tva = abs(self.montant_tva)

        # Immobilisation automatique si Bien > 500€
        if self.categorisation == 'bien' and self.montant_ttc and self.montant_ttc > 500:
            self.immobilisation = True
            self.categorisation = 'immobilisation'
        super().save(*args, **kwargs)

    @property
    def annee(self):
        return self.date_operation.year

    @property
    def mois(self):
        return self.date_operation.month
