"""Calcula el impacto y revierte todos los cambios antes de salir."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.elecciones.models import Eleccion
from apps.padron.services import calcular_mesas_automaticas_eleccion


class Command(BaseCommand):
    help = "Simula el recálculo del padrón y sus autoridades sin guardar cambios."

    def add_arguments(self, parser):
        parser.add_argument("--eleccion", required=True, type=int)

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                eleccion = Eleccion.objects.get(pk=options["eleccion"])
                resultado = calcular_mesas_automaticas_eleccion(eleccion, recalcular_sedes=False, confirmar_afectadas=True)
                self.stdout.write(f"Mesas: {resultado['mesas']}; electores: {resultado['electores']}; "
                                  f"autoridades que quedarían vacantes: {resultado.get('autoridades_vacantes', 0)}.")
                for fila in resultado.get("detalle_autoridades_vacantes", []):
                    self.stdout.write(f"- {fila['elector']} · {fila['mesa']} · {fila['turno']}")
                self.stdout.write("Simulación: no se guardaron cambios.")
                transaction.set_rollback(True)
        except (Eleccion.DoesNotExist, ValueError) as error:
            raise CommandError(str(error))
