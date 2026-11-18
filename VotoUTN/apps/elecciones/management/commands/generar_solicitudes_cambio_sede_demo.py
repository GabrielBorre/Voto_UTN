from django.core.management.base import BaseCommand

from apps.elecciones.demo_generadores import eleccion_actual_demo, generar_solicitudes_demo


class Command(BaseCommand):
    help = "Completa hasta treinta solicitudes de estudiantes sin designación de autoridad."

    def handle(self, *args, **options):
        eleccion = eleccion_actual_demo()
        creadas = generar_solicitudes_demo(eleccion)
        self.stdout.write(f"Elección: {eleccion.nombre}. Solicitudes creadas: {creadas}.")
