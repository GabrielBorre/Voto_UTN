from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.elecciones.models import Eleccion
from apps.partidos.services import sincronizar_puestos_claustro


class Command(BaseCommand):
    help = (
        "Genera los puestos de una o todas las elecciones en preparación a partir de los parámetros "
        "de puestos a elegir (claustros, cantidades y alcance departamental o general)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "eleccion_id",
            type=int,
            nargs="?",
            help="Identificador de una elección en preparación; si se omite, procesa todas.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        eleccion_id = options["eleccion_id"]
        if eleccion_id is None:
            elecciones = Eleccion.objects.filter(estado=Eleccion.Estado.EN_PREPARACION)
        else:
            try:
                eleccion = Eleccion.objects.get(pk=eleccion_id)
            except Eleccion.DoesNotExist as error:
                raise CommandError("No existe la elección indicada.") from error
            if eleccion.estado != Eleccion.Estado.EN_PREPARACION:
                raise CommandError("Solo se pueden generar puestos para una elección en preparación.")
            elecciones = Eleccion.objects.filter(pk=eleccion.pk)

        total = {"creados": 0, "actualizados": 0, "eliminados": 0}
        for eleccion in elecciones:
            for eleccion_claustro in eleccion.elecciones_claustro.select_related("eleccion", "claustro"):
                for clave, cantidad in sincronizar_puestos_claustro(eleccion_claustro).items():
                    total[clave] += cantidad

        if options["verbosity"] >= 1:
            alcance = f"la elección {eleccion_id}" if eleccion_id is not None else "las elecciones en preparación"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Puestos de {alcance}: {total['creados']} creados, "
                    f"{total['actualizados']} actualizados, {total['eliminados']} eliminados."
                )
            )
