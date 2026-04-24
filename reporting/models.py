from django.db import models


class DeclarationTVA(models.Model):
    """
    Déclaration TVA mensuelle.
    Calquée sur le formulaire CA3 de impots.gouv.fr.
    """
    SWITCH_CHOICES = [
        ('operation', 'Date d\'opération bancaire'),
        ('facture', 'Date de facture'),
    ]

    periode = models.CharField(
        max_length=6, unique=True,
        help_text="Format AAAAMM (ex: 202406)"
    )
    switch_calcul = models.CharField(
        max_length=20, choices=SWITCH_CHOICES, default='operation',
        help_text="Base de calcul : date d'opération ou date de facture"
    )
    finalisee = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ─── Section A : Opérations imposables (HT) ─────────────────────────────
    # A — Opérations imposables
    ligne_A1 = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="A1 — Ventes et prestations de services HT"
    )
    ligne_A2 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="A2 — Autres opérations imposables")
    ligne_A3 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="A3 — Importations")

    # B — Opérations diverses
    ligne_B2 = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="B2 — Acquisitions intracommunautaires HT"
    )

    # E — Opérations non imposables
    ligne_E2 = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="E2 — Autres opérations non imposables (cotisations)"
    )

    # ─── Section B : TVA brute ───────────────────────────────────────────────
    ligne_16 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="16 — Total TVA brute due")
    ligne_17 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="17 — Dont TVA sur acquisitions intracommunautaires")

    # ─── TVA déductible ──────────────────────────────────────────────────────
    ligne_20 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="20 — Autres biens et services (TVA factures achats)")
    ligne_21 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="21 — Autre TVA à déduire")
    ligne_22 = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="22 — Report du crédit (ligne 27 du mois précédent)"
    )
    ligne_23 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="23 — Total TVA déductible (19+20+21+22)")

    # ─── Crédits ou taxe à payer ─────────────────────────────────────────────
    ligne_25 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="25 — Crédit de TVA (23-16)")
    ligne_27 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="27 — Crédit à reporter")
    ligne_28 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="28 — TVA nette due (16-23)")
    ligne_32 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="32 — Total à payer")

    # ─── Validation et Justificatifs ────────────────────────────────────────
    lien_declaration = models.URLField(max_length=500, blank=True, null=True, help_text="Lien vers la déclaration de TVA")
    lien_accuse_reception = models.URLField(max_length=500, blank=True, null=True, help_text="Lien vers l'accusé de réception")
    lien_ordre_paiement = models.URLField(max_length=500, blank=True, null=True, help_text="Lien vers l'ordre de paiement")
    date_validation = models.DateTimeField(null=True, blank=True, help_text="Date à laquelle la déclaration a été figée")

    class Meta:
        ordering = ['-periode']
        verbose_name = "Déclaration TVA"
        verbose_name_plural = "Déclarations TVA"

    def __str__(self):
        annee = self.periode[:4]
        mois = self.periode[4:]
        return f"Déclaration TVA {mois}/{annee}"

    @property
    def libelle_periode(self):
        from datetime import date
        import calendar
        annee = int(self.periode[:4])
        mois = int(self.periode[4:])
        mois_noms = [
            '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        return f"{mois_noms[mois]} {annee}"
