from django.core.management.base import BaseCommand

from supervision.sync import synchroniser_tout


class Command(BaseCommand):
    help = "Synchronise alertes, états machines et contrôle IP depuis Zabbix."

    def handle(self, *args, **options):
        stats = synchroniser_tout()
        self.stdout.write(
            self.style.SUCCESS(
                "Sync terminée — "
                f"licences={stats['licences']} "
                f"alertes_creees={stats['alertes_creees']} "
                f"alertes_maj={stats['alertes_maj']} "
                f"ip_ecarts={stats['ip_ecarts']} "
                f"erreurs={stats['erreurs']}"
            )
        )
