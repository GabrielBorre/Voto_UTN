import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from apps.notificaciones.calendario import procesar_calendario


class Command(BaseCommand):
    help = "Procesa mensajes programados. --continuo mantiene el worker activo."

    def add_arguments(self, parser):
        parser.add_argument("--continuo", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            self.stdout.write(f"Programaciones procesadas: {procesar_calendario()}")
            if not options["continuo"]:
                return
            time.sleep(60)
