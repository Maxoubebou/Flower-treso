from django import forms
from .models import DemandeNDF, LigneNDF

class DemandeNDFForm(forms.ModelForm):
    class Meta:
        model = DemandeNDF
        fields = ['prenom_beneficiaire', 'nom_beneficiaire', 'libelle', 'type_frais', 'rib_beneficiaire', 'commentaire_demandeur']
        widgets = {
            'prenom_beneficiaire': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Prénom',
                'required': 'required'
            }),
            'nom_beneficiaire': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom',
                'required': 'required'
            }),
            'libelle': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Déplacement AG Lyon / Achat fournitures bureau',
                'required': 'required'
            }),
            'type_frais': forms.Select(attrs={
                'class': 'form-control',
                'onchange': 'toggleFraisType(this.value)'
            }),
            'rib_beneficiaire': forms.TextInput(attrs={
                'class': 'form-control font-mono',
                'placeholder': 'FR76 ...',
                'required': 'required'
            }),
            'commentaire_demandeur': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Précisions supplémentaires...',
                'rows': 2
            }),
        }

