from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.elecciones.models import Eleccion
from apps.partidos.services import habilitar_puestos_departamentales_predeterminados


class Command(BaseCommand):
    help = "Crea los puestos departamentales predeterminados faltantes para una elección."

    def add_arguments(self, parser):
        parser.add_argument("eleccion_id", type=int, help="Identificador de la elección en preparación.")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            eleccion = Eleccion.objects.get(pk=options["eleccion_id"])
        except Eleccion.DoesNotExist as error:
            raise CommandError("No existe la elección indicada.") from error

        if eleccion.estado != Eleccion.Estado.EN_PREPARACION:
            raise CommandError("Solo se pueden habilitar puestos para una elección en preparación.")

        puestos_creados = []
        claustros = eleccion.elecciones_claustro.select_related("claustro")
        for eleccion_claustro in claustros:
            puestos_creados.extend(habilitar_puestos_departamentales_predeterminados(eleccion_claustro))

        if options["verbosity"] >= 1:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Se crearon {len(puestos_creados)} puestos departamentales para la eleccion {eleccion.pk}."
                )
            )
