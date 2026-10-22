import secrets
import string

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import Client


def generer_cle_licence():
    """Génère une clé au format SPV-XXXX-XXXX-XXXX-XXXX (RG-01)."""
    alphabet = string.ascii_uppercase + string.digits
    segments = [
        "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)
    ]
    return "SPV-" + "-".join(segments)


def generer_psk():
    """Génère une clé PSK hexadécimale pour Zabbix (64 caractères)."""
    return secrets.token_hex(32)


def generer_identifiant():
    """Identifiant unique servant de Hostname et d'identité PSK Zabbix."""
    return "spv-" + secrets.token_hex(8)


class Licence(models.Model):
    """Licence Supervya : 1 licence = 1 machine = 1 adresse IP."""

    class Etat(models.TextChoices):
        GENEREE = "GENEREE", "Générée"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDUE = "SUSPENDUE", "Suspendue"
        EXPIREE = "EXPIREE", "Expirée"
        REVOQUEE = "REVOQUEE", "Révoquée"

    class Systeme(models.TextChoices):
        LINUX = "linux", "Linux"
        WINDOWS = "windows", "Windows"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="licences",
        verbose_name="client",
    )
    cle = models.CharField(
        "clé de licence",
        max_length=23,
        unique=True,
        editable=False,
        default=generer_cle_licence,
    )
    identifiant = models.CharField(
        "identifiant",
        max_length=64,
        unique=True,
        editable=False,
        default=generer_identifiant,
        help_text="Hostname Zabbix et identité PSK.",
    )
    psk = models.CharField(
        "clé PSK",
        max_length=64,
        editable=False,
        default=generer_psk,
    )
    etat = models.CharField(
        "état",
        max_length=20,
        choices=Etat.choices,
        default=Etat.GENEREE,
        db_index=True,
    )
    systeme = models.CharField(
        "système",
        max_length=20,
        choices=Systeme.choices,
        default=Systeme.LINUX,
    )
    adresse_ip = models.GenericIPAddressField(
        "adresse IP",
        null=True,
        blank=True,
        help_text="IP enregistrée à l'activation (RG-03).",
    )
    zabbix_hostid = models.CharField(
        "ID hôte Zabbix",
        max_length=32,
        blank=True,
        default="",
    )
    seuil_cpu = models.PositiveSmallIntegerField(
        "seuil CPU (%)",
        default=90,
        help_text="Macro {$CPU.UTIL.CRIT}",
    )
    seuil_memoire = models.PositiveSmallIntegerField(
        "seuil mémoire (%)",
        default=90,
        help_text="Macro {$MEMORY.UTIL.MAX}",
    )
    seuil_disque = models.PositiveSmallIntegerField(
        "seuil disque (%)",
        default=90,
        help_text="Macro {$VFS.FS.PUSED.MAX.CRIT}",
    )
    date_creation = models.DateTimeField("date de création", auto_now_add=True)
    date_activation = models.DateTimeField(
        "date d'activation",
        null=True,
        blank=True,
    )
    date_expiration = models.DateTimeField(
        "date d'expiration",
        null=True,
        blank=True,
    )
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "licence"
        verbose_name_plural = "licences"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.cle} ({self.get_etat_display()})"

    def clean(self):
        for champ, valeur in (
            ("seuil_cpu", self.seuil_cpu),
            ("seuil_memoire", self.seuil_memoire),
            ("seuil_disque", self.seuil_disque),
        ):
            if valeur is not None and not 1 <= valeur <= 100:
                raise ValidationError({champ: "Le seuil doit être entre 1 et 100."})

    @property
    def est_liee(self):
        return self.etat != self.Etat.GENEREE and bool(self.zabbix_hostid)

    @property
    def est_exploitable(self):
        return self.etat == self.Etat.ACTIVE

    def marquer_expiree_si_necessaire(self):
        if (
            self.etat == self.Etat.ACTIVE
            and self.date_expiration
            and self.date_expiration <= timezone.now()
        ):
            self.etat = self.Etat.EXPIREE
            self.save(update_fields=["etat"])
            return True
        return False
