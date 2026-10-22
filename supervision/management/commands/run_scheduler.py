import time

from django.core.management.base import BaseCommand

from supervision.sync import synchroniser_tout


class Command(BaseCommand):
    help = (
        "Boucle de synchronisation toutes les 30 secondes "
        "(alternative simple à Celery Beat)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help="Intervalle en secondes (défaut : 30).",
        )

    def handle(self, *args, **options):
        interval = max(5, options["interval"])
        self.stdout.write(
            self.style.NOTICE(f"Planificateur Supervya démarré (intervalle={interval}s).")
        )
        while True:
            try:
                stats = synchroniser_tout()
                self.stdout.write(
                    f"sync ok licences={stats['licences']} "
                    f"erreurs={stats['erreurs']}"
                )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"sync erreur: {exc}"))
            time.sleep(interval)
