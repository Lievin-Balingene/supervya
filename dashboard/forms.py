from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone

from accounts.models import Client, Utilisateur
from licensing.models import Licence


class ConnexionForm(AuthenticationForm):
    username = forms.CharField(
        label="Identifiant",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Mot de passe",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ("nom", "email_contact", "email_alertes", "actif")
        labels = {
            "nom": "Raison sociale",
            "email_contact": "E-mail de contact",
            "email_alertes": "E-mail des alertes",
            "actif": "Compte actif",
        }


class UtilisateurClientForm(forms.ModelForm):
    mot_de_passe = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput,
        min_length=8,
    )

    class Meta:
        model = Utilisateur
        fields = ("username", "email", "client", "first_name", "last_name")
        labels = {
            "username": "Identifiant",
            "email": "E-mail",
            "client": "Client",
            "first_name": "Prénom",
            "last_name": "Nom",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(actif=True).order_by("nom")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["mot_de_passe"])
        user.is_staff = False
        if commit:
            user.save()
        return user


class LicenceCreateForm(forms.ModelForm):
    duree_jours = forms.IntegerField(
        label="Durée (jours)",
        min_value=1,
        initial=365,
        help_text="Date d'expiration = aujourd'hui + durée.",
    )

    class Meta:
        model = Licence
        fields = ("client", "systeme", "seuil_cpu", "seuil_memoire", "seuil_disque", "notes")
        labels = {
            "client": "Client",
            "systeme": "Système",
            "seuil_cpu": "Seuil CPU (%)",
            "seuil_memoire": "Seuil mémoire (%)",
            "seuil_disque": "Seuil disque (%)",
            "notes": "Notes",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(actif=True).order_by("nom")

    def save(self, commit=True):
        licence = super().save(commit=False)
        licence.date_expiration = timezone.now() + timezone.timedelta(
            days=self.cleaned_data["duree_jours"]
        )
        if commit:
            licence.save()
        return licence


class LicenceIpForm(forms.Form):
    adresse_ip = forms.GenericIPAddressField(label="Nouvelle adresse IP")
