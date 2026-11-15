from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Migra la instancia y carga la demo inicial solo en una base nueva."

    def handle(self, *args, **options):
        marcador = Path(settings.MEDIA_ROOT) / ".inicializacion_demo_pendiente"
        if not marcador.exists() and "django_migrations" not in connection.introspection.table_names():
            marcador.parent.mkdir(parents=True, exist_ok=True)
            marcador.touch()

        call_command("migrate", interactive=False, stdout=self.stdout)
        if marcador.exists():
            call_command("seed_demo_inicial", stdout=self.stdout)
            marcador.unlink()
        else:
            self.stdout.write("Base existente: no se ejecuta la carga inicial de demostracion.")
