from django.core.management.base import BaseCommand

from apps.elecciones.servicios.notificaciones import procesar_envios_pendientes


class Command(BaseCommand):
    help = "Procesa los envios de notificaciones pendientes."

    def handle(self, *args, **options):
        self.stdout.write(f"Notificaciones procesadas: {procesar_envios_pendientes()}")
