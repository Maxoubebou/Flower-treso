from django import forms
from .models import DemandeNDF, LigneNDF

class DemandeNDFForm(forms.ModelForm):
    class Meta:
        model = DemandeNDF
        fields = ['email', 'rib_beneficiaire', 'justificatif']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'prenom.nom@ouest-insa.fr',
                'required': 'required'
            }),
            'rib_beneficiaire': forms.TextInput(attrs={
                'class': 'form-control font-mono',
                'placeholder': 'FR76 ...',
                'required': 'required'
            }),
            'justificatif': forms.FileInput(attrs={
                'class': 'form-control',
                'required': 'required',
                'accept': 'image/*,application/pdf'
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email.endswith('@ouest-insa.fr'):
            raise forms.ValidationError("L'adresse email doit être une adresse @ouest-insa.fr")
        return email
