from django.contrib.auth.models import AbstractUser
from django.db import models


class Client(models.Model):
    """Organisation cliente abonnée à Supervya."""

    nom = models.CharField("nom", max_length=200)
    email_contact = models.EmailField("e-mail de contact")
    email_alertes = models.EmailField(
        "e-mail des alertes",
        help_text="Adresse destinataire des notifications d'alerte.",
    )
    actif = models.BooleanField("actif", default=True)
    date_creation = models.DateTimeField("date de création", auto_now_add=True)

    class Meta:
        verbose_name = "client"
        verbose_name_plural = "clients"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class Utilisateur(AbstractUser):
    """Compte utilisateur Supervya (client ou administrateur)."""

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="utilisateurs",
        null=True,
        blank=True,
        verbose_name="client",
        help_text="Laisser vide pour un administrateur interne.",
    )

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"

    def __str__(self):
        return self.get_username()

    @property
    def est_client(self):
        return self.client_id is not None and not self.is_staff
