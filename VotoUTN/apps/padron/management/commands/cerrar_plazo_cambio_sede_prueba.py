"""Adelanta el cierre de solicitudes en una elección de prueba."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.elecciones.models import Eleccion
from apps.padron.models import SolicitudCambioSede


class Command(BaseCommand):
    help = "Simula o cambia la fecha límite de solicitudes de sede para una elección de prueba."

    def add_arguments(self, parser):
        parser.add_argument("--eleccion", required=True, type=int)
        parser.add_argument("--fecha", help="Fecha de cierre AAAA-MM-DD; por defecto, ayer.")
        parser.add_argument("--aplicar", action="store_true", help="Guardar el cambio de fecha.")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            fecha = date.fromisoformat(options["fecha"]) if options["fecha"] else timezone.localdate() - timedelta(days=1)
        except ValueError as error:
            raise CommandError("La fecha debe tener formato AAAA-MM-DD.") from error
        eleccion = Eleccion.objects.select_for_update().filter(pk=options["eleccion"]).first()
        if not eleccion:
            raise CommandError("La elección no existe.")
        if eleccion.estado != Eleccion.Estado.PUBLICADA or eleccion.autoridades_confirmadas_en:
            raise CommandError("La elección debe estar publicada y sus autoridades sin confirmar.")
        anterior = eleccion.fecha_cierre_solicitudes_cambio_sede
        eleccion.fecha_cierre_solicitudes_cambio_sede = fecha
        try:
            eleccion.full_clean()
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        pendientes = SolicitudCambioSede.objects.filter(registro_padron__eleccion=eleccion, estado="pendiente").count()
        self.stdout.write(f"Elección: {eleccion.nombre}; cierre: {anterior} → {fecha}; solicitudes pendientes: {pendientes}.")
        if not options["aplicar"]:
            self.stdout.write("Simulación: no se guardaron cambios. Agregá --aplicar para guardar la fecha.")
            return
        eleccion.save(update_fields=("fecha_cierre_solicitudes_cambio_sede",))
        self.stdout.write(self.style.SUCCESS("Fecha actualizada. Las solicitudes pendientes deben resolverse antes de confirmar autoridades."))
