from django.contrib import admin

from .models import Alerte, EtatMachine


@admin.register(Alerte)
class AlerteAdmin(admin.ModelAdmin):
    list_display = (
        "titre",
        "licence",
        "severite",
        "active",
        "email_envoye",
        "date_debut",
        "date_fin",
    )
    list_filter = ("active", "severite", "email_envoye")
    search_fields = ("titre", "message", "licence__cle", "licence__identifiant")
    readonly_fields = (
        "licence",
        "zabbix_eventid",
        "titre",
        "message",
        "severite",
        "active",
        "email_envoye",
        "date_debut",
        "date_fin",
        "date_creation",
        "date_mise_a_jour",
    )

    def has_add_permission(self, request):
        return False


@admin.register(EtatMachine)
class EtatMachineAdmin(admin.ModelAdmin):
    list_display = (
        "licence",
        "statut",
        "agent_disponible",
        "cpu_pct",
        "memoire_pct",
        "disque_pct",
        "derniere_donnees",
        "date_mise_a_jour",
    )
    list_filter = ("statut", "agent_disponible")
    search_fields = ("licence__cle", "licence__identifiant")
    readonly_fields = (
        "licence",
        "statut",
        "agent_disponible",
        "cpu_pct",
        "memoire_pct",
        "disque_pct",
        "derniere_donnees",
        "date_mise_a_jour",
    )

    def has_add_permission(self, request):
        return False
