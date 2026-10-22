from django.contrib import admin, messages
from django.utils import timezone

from .models import Licence


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

    @admin.action(description="Suspendre les licences sélectionnées")
    def action_suspendre(self, request, queryset):
        updated = queryset.exclude(
            etat__in=[Licence.Etat.REVOQUEE, Licence.Etat.GENEREE]
        ).update(etat=Licence.Etat.SUSPENDUE)
        self.message_user(
            request,
            f"{updated} licence(s) suspendue(s).",
            messages.SUCCESS,
        )

    @admin.action(description="Révoquer les licences sélectionnées")
    def action_revoquer(self, request, queryset):
        updated = queryset.exclude(etat=Licence.Etat.REVOQUEE).update(
            etat=Licence.Etat.REVOQUEE
        )
        self.message_user(
            request,
            f"{updated} licence(s) révoquée(s).",
            messages.WARNING,
        )

    @admin.action(description="Renouveler (réactiver) les licences sélectionnées")
    def action_renouveler(self, request, queryset):
        count = 0
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
            count += 1
        self.message_user(
            request,
            f"{count} licence(s) renouvelée(s).",
            messages.SUCCESS,
        )
