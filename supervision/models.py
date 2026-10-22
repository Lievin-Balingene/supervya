from django.db import models

from licensing.models import Licence


class Alerte(models.Model):
    """Alerte Supervya synchronisée depuis les problèmes Zabbix."""

    class Severite(models.TextChoices):
        INFORMATION = "info", "Information"
        AVERTISSEMENT = "warning", "Avertissement"
        MOYENNE = "average", "Moyenne"
        HAUTE = "high", "Haute"
        DISASTER = "disaster", "Critique"
        IP_ECART = "ip_mismatch", "Écart d'adresse IP"

    licence = models.ForeignKey(
        Licence,
        on_delete=models.CASCADE,
        related_name="alertes",
        verbose_name="licence",
    )
    zabbix_eventid = models.CharField(
        "ID événement Zabbix",
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )
    titre = models.CharField("titre", max_length=255)
    message = models.TextField("message", blank=True)
    severite = models.CharField(
        "sévérité",
        max_length=20,
        choices=Severite.choices,
        default=Severite.AVERTISSEMENT,
    )
    active = models.BooleanField("active", default=True, db_index=True)
    lue = models.BooleanField("lue", default=False)
    email_envoye = models.BooleanField("e-mail envoyé", default=False)
    date_debut = models.DateTimeField("date de début")
    date_fin = models.DateTimeField("date de fin", null=True, blank=True)
    date_creation = models.DateTimeField("date de création", auto_now_add=True)
    date_mise_a_jour = models.DateTimeField("dernière mise à jour", auto_now=True)

    class Meta:
        verbose_name = "alerte"
        verbose_name_plural = "alertes"
        ordering = ["-date_debut"]
        constraints = [
            models.UniqueConstraint(
                fields=["licence", "zabbix_eventid"],
                condition=~models.Q(zabbix_eventid=""),
                name="uniq_alerte_licence_eventid",
            )
        ]

    def __str__(self):
        statut = "active" if self.active else "résolue"
        return f"{self.titre} ({statut})"


class EtatMachine(models.Model):
    """État de disponibilité / santé d'une machine liée à une licence."""

    class Statut(models.TextChoices):
        OK = "ok", "OK"
        ATTENTION = "attention", "Attention"
        CRITIQUE = "critique", "Critique"
        HORS_LIGNE = "hors_ligne", "Hors ligne"
        INCONNU = "inconnu", "Inconnu"

    licence = models.OneToOneField(
        Licence,
        on_delete=models.CASCADE,
        related_name="etat_machine",
        verbose_name="licence",
    )
    statut = models.CharField(
        "statut",
        max_length=20,
        choices=Statut.choices,
        default=Statut.INCONNU,
    )
    agent_disponible = models.BooleanField("agent disponible", default=False)
    cpu_pct = models.FloatField("CPU (%)", null=True, blank=True)
    memoire_pct = models.FloatField("mémoire (%)", null=True, blank=True)
    disque_pct = models.FloatField("disque (%)", null=True, blank=True)
    derniere_donnees = models.DateTimeField(
        "dernières données",
        null=True,
        blank=True,
    )
    date_mise_a_jour = models.DateTimeField("dernière mise à jour", auto_now=True)

    class Meta:
        verbose_name = "état machine"
        verbose_name_plural = "états machines"

    def __str__(self):
        return f"{self.licence.identifiant} — {self.get_statut_display()}"

    @property
    def couleur(self):
        """Couleur tableau de bord : vert / orange / rouge."""
        mapping = {
            self.Statut.OK: "vert",
            self.Statut.ATTENTION: "orange",
            self.Statut.CRITIQUE: "rouge",
            self.Statut.HORS_LIGNE: "rouge",
            self.Statut.INCONNU: "orange",
        }
        return mapping.get(self.statut, "orange")
