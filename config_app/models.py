from django.db import models


class LigneBudgetaire(models.Model):
    nom = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = "Ligne budgétaire"
        verbose_name_plural = "Lignes budgétaires"

    def __str__(self):
        return self.nom


class TypeFactureVente(models.Model):
    """Types de factures de vente (configurable en paramètres)."""
    SUFFIXE_CHOICES = [
        ('A', 'Acompte'),
        ('S', 'Solde'),
        ('C', 'Cotisation'),
        ('SU', 'Subvention'),
        ('AV', 'Avoir'),
        ('R', 'Refacturation'),
    ]
    nom = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    suffixe = models.CharField(max_length=5, choices=SUFFIXE_CHOICES)
    taux_tva_defaut = models.DecimalField(max_digits=5, decimal_places=2, default=20.00)
    est_cotisation = models.BooleanField(default=False)  # TVA 0%
    est_subvention = models.BooleanField(default=False)  # Préfixe S
    active = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = "Type de facture de vente"
        verbose_name_plural = "Types de factures de vente"

    def __str__(self):
        return self.nom


class TypeAchat(models.Model):
    """Types de factures d'achat (configurable en paramètres)."""
    SUFFIXE_CHOICES = [
        ('F', 'Fournisseur'),
        ('NF', 'Note de frais'),
    ]
    nom = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    suffixe = models.CharField(max_length=5, choices=SUFFIXE_CHOICES)
    active = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = "Type d'achat"
        verbose_name_plural = "Types d'achat"

    def __str__(self):
        return self.nom


class ParametreTVA(models.Model):
    """Taux de TVA disponibles et leurs commentaires d'aide."""
    taux = models.DecimalField(max_digits=5, decimal_places=2, unique=True)
    libelle = models.CharField(max_length=100)
    commentaire = models.TextField(blank=True, help_text="Cas d'application affichés à l'utilisateur")
    actif = models.BooleanField(default=True)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'taux']
        verbose_name = "Paramètre TVA"
        verbose_name_plural = "Paramètres TVA"

    def __str__(self):
        return f"{self.taux}% — {self.libelle}"


class ParametreCotisation(models.Model):
    """
    Taux de cotisations URSSAF, modifiables en paramètres.
    Un enregistrement par type de cotisant (junior / etudiant).
    """
    TYPE_CHOICES = [
        ('junior', 'Junior-Entreprise'),
        ('etudiant', 'Étudiant'),
    ]
    type_cotisant = models.CharField(max_length=20, choices=TYPE_CHOICES, unique=True)
    base_urssaf = models.DecimalField(max_digits=8, decimal_places=2, default=48.08,
                                      help_text="Base Urssaf par JEH (€)")
    assurance_maladie = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                            help_text="Taux assurance maladie (%)")
    accident_travail = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                           help_text="Taux accident du travail (%)")
    vieillesse_plafonnee = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                               help_text="Taux vieillesse plafonnée (%)")
    vieillesse_deplafonnee = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text="Taux vieillesse déplafonnée (%)")
    allocations_familiales = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                                 help_text="Taux allocations familiales (%)")
    csg_deductible = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                         help_text="Taux CSG déductible (%)")
    csg_non_deductible = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                             help_text="Taux CSG non déductible (%)")

    class Meta:
        verbose_name = "Paramètre cotisation"
        verbose_name_plural = "Paramètres cotisations"

    def __str__(self):
        return f"Cotisations {self.get_type_cotisant_display()}"

    def taux_total(self):
        return (self.assurance_maladie + self.accident_travail + self.vieillesse_plafonnee
                + self.vieillesse_deplafonnee + self.allocations_familiales
                + self.csg_deductible + self.csg_non_deductible)
