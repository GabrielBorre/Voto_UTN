from django.core.management.base import BaseCommand, CommandError

from apps.elecciones.demo_generadores import eleccion_actual_demo, generar_justificativos_demo


class ComandoJustificativosDemo(BaseCommand):
    ausencia = None

    def add_arguments(self, parser):
        parser.add_argument("--cantidad", type=int, default=2)
        parser.add_argument("--semilla", type=int, default=None)

    def handle(self, *args, **options):
        cantidad = options["cantidad"]
        if cantidad < 0:
            raise CommandError("La cantidad no puede ser negativa.")
        eleccion = eleccion_actual_demo()
        creados = generar_justificativos_demo(eleccion, self.ausencia, cantidad, options["semilla"])
        self.stdout.write(f"Elección: {eleccion.nombre}. Justificativos creados: {creados}.")
        if creados < cantidad:
            self.stderr.write(self.style.WARNING(
                f"Solo se crearon {creados} de {cantidad}: no hay suficientes registros elegibles."
            ))
