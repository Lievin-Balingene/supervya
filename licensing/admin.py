from django.contrib import admin, messages
from django.utils import timezone

from supervision.zabbix_client import ZabbixAPIError

from .models import Licence
from .services import synchroniser_etat_hote_zabbix


@admin.register(Licence)
class LicenceAdmin(admin.ModelAdmin):
    list_display = (
        "cle",
        "client",
        "etat",
        "systeme",
        "adresse_ip",
        "identifiant",
        "date_creation",
        "date_expiration",
    )
    list_filter = ("etat", "systeme", "client")
    search_fields = ("cle", "identifiant", "adresse_ip", "client__nom")
    readonly_fields = (
        "cle",
        "identifiant",
        "psk",
        "adresse_ip",
        "zabbix_hostid",
        "date_creation",
        "date_activation",
    )
    actions = (
        "action_suspendre",
        "action_revoquer",
        "action_renouveler",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "client",
                    "systeme",
                    "etat",
                    "date_expiration",
                    "notes",
                )
            },
        ),
        (
            "Identifiants (générés automatiquement)",
            {
                "fields": (
                    "cle",
                    "identifiant",
                    "psk",
                    "adresse_ip",
                    "zabbix_hostid",
                    "date_creation",
                    "date_activation",
                )
            },
        ),
        (
            "Seuils d'alerte (%)",
            {
                "fields": ("seuil_cpu", "seuil_memoire", "seuil_disque"),
            },
        ),
    )

    def _sync_zabbix(self, request, licences):
        erreurs = 0
        for licence in licences:
            try:
                synchroniser_etat_hote_zabbix(licence)
            except ZabbixAPIError:
                erreurs += 1
        if erreurs:
            self.message_user(
                request,
                f"{erreurs} synchronisation(s) Zabbix en échec.",
                messages.ERROR,
            )

    @admin.action(description="Suspendre les licences sélectionnées")
    def action_suspendre(self, request, queryset):
        cibles = list(
            queryset.exclude(
                etat__in=[Licence.Etat.REVOQUEE, Licence.Etat.GENEREE]
            )
        )
        for licence in cibles:
            licence.etat = Licence.Etat.SUSPENDUE
            licence.save(update_fields=["etat"])
        self._sync_zabbix(request, cibles)
        self.message_user(
            request,
            f"{len(cibles)} licence(s) suspendue(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Révoquer les licences sélectionnées")
    def action_revoquer(self, request, queryset):
        cibles = list(queryset.exclude(etat=Licence.Etat.REVOQUEE))
        for licence in cibles:
            licence.etat = Licence.Etat.REVOQUEE
            licence.save(update_fields=["etat"])
        self._sync_zabbix(request, cibles)
        self.message_user(
            request,
            f"{len(cibles)} licence(s) révoquée(s).",
            messages.WARNING,
        )

    @admin.action(description="Renouveler (réactiver) les licences sélectionnées")
    def action_renouveler(self, request, queryset):
        cibles = []
        for licence in queryset.filter(
            etat__in=[
                Licence.Etat.SUSPENDUE,
                Licence.Etat.EXPIREE,
            ]
        ):
            licence.etat = Licence.Etat.ACTIVE
            if licence.date_expiration and licence.date_expiration <= timezone.now():
                licence.date_expiration = timezone.now() + timezone.timedelta(days=365)
            licence.save(update_fields=["etat", "date_expiration"])
            cibles.append(licence)
        self._sync_zabbix(request, cibles)
        self.message_user(
            request,
            f"{len(cibles)} licence(s) renouvelée(s).",
            messages.SUCCESS,
        )
