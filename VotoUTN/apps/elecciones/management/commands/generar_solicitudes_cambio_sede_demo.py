from django.core.management.base import BaseCommand

from apps.elecciones.demo_generadores import eleccion_actual_demo, generar_solicitudes_demo


class Command(BaseCommand):
    help = (
        "Completa las solicitudes de estudiantes sin designación de autoridad. "
        "En la instancia 2: hasta treinta de Sistemas, veinte de Industrial y cuatro de Naval; "
        "Industrial y Naval van de Campus a Medrano. En las demás: hasta treinta estudiantes."
    )

    def handle(self, *args, **options):
        eleccion = eleccion_actual_demo()
        creadas = generar_solicitudes_demo(eleccion)
        self.stdout.write(f"Elección: {eleccion.nombre}. Solicitudes creadas: {creadas}.")
