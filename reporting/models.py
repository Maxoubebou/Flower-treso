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
    ligne_A4 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="A4 — Sorties de régime")
    ligne_A5 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="A5 — Autres opérations")

    # B — Opérations diverses
    ligne_B1 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="B1 — Livraisons intracommunautaires")
    ligne_B2 = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="B2 — Acquisitions intracommunautaires HT"
    )
    ligne_B3 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="B3 — Autres opérations non imposables")
    ligne_B4 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="B4 — Autres catégories")
    ligne_B5 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="B5 — Autres catégories")

    # E — Opérations non imposables
    ligne_E1 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="E1 — Exportations hors UE")
    ligne_E2 = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="E2 — Autres opérations non imposables (cotisations)"
    )

    # ─── Section B : TVA brute ───────────────────────────────────────────────
    ligne_08_base = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                        help_text="08 — Base imposable taux normal 20%")
    ligne_08_taxe = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                        help_text="08 — TVA due taux normal 20%")
    ligne_09_base = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                        help_text="09 — Base imposable taux réduit 10%")
    ligne_09_taxe = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                        help_text="09 — TVA due taux réduit 10%")
    ligne_09b_base = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                         help_text="09b — Base imposable taux réduit 5,5%")
    ligne_09b_taxe = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                         help_text="09b — TVA due taux réduit 5,5%")
    ligne_16 = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                   help_text="16 — Total TVA brute due (08+09+09b)")
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
    ligne_22_modifiee_manuellement = models.BooleanField(
        default=False,
        help_text="Indique si la ligne 22 a été saisie manuellement"
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
