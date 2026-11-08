from django.core.management.base import BaseCommand, CommandError

from apps.elecciones.demo_generadores import eleccion_actual_demo, generar_solicitudes_demo


class Command(BaseCommand):
    help = "Genera solicitudes de cambio de sede de demo para la elección publicada."

    def add_arguments(self, parser):
        parser.add_argument("--cantidad", type=int, default=70)
        parser.add_argument("--semilla", type=int, default=None)

    def handle(self, *args, **options):
        cantidad = options["cantidad"]
        if cantidad < 0:
            raise CommandError("La cantidad no puede ser negativa.")
        eleccion = eleccion_actual_demo()
        creadas = generar_solicitudes_demo(eleccion, cantidad, options["semilla"])
        self.stdout.write(f"Elección: {eleccion.nombre}. Solicitudes creadas: {creadas}.")
