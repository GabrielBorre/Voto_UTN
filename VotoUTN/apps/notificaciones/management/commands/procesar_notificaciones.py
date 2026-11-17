import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.notificaciones.services import procesar_envios_pendientes, procesar_lotes_pendientes


class Command(BaseCommand):
    help = "Genera lotes y procesa correos pendientes con reintentos y prioridad."

    def add_arguments(self, parser):
        parser.add_argument("--continuo", action="store_true")
        parser.add_argument("--intervalo", type=int, default=2)
        parser.add_argument("--limite", type=int, default=100)

    def handle(self, *args, **options):
        if options["intervalo"] < 1 or options["limite"] < 1:
            raise CommandError("El intervalo y el limite deben ser mayores que cero.")
        self.stdout.write("Procesador de notificaciones iniciado.")
        while True:
            close_old_connections()
            lotes = procesar_lotes_pendientes()
            envios = procesar_envios_pendientes(limite=options["limite"])
            if lotes or envios or not options["continuo"]:
                self.stdout.write(f"Lotes procesados: {lotes}. Notificaciones procesadas: {envios}.")
            if not options["continuo"]:
                break
            time.sleep(options["intervalo"])
