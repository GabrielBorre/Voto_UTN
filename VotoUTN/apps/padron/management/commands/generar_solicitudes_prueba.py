"""Genera solicitudes de prueba concentradas para ejercitar el impacto en mesas."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from apps.elecciones.models import Eleccion
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron, SolicitudCambioSede
from apps.padron.services import solicitudes_cambio_sede_habilitadas


class Command(BaseCommand):
    help = "Previsualiza o crea solicitudes de cambio de sede para una elección publicada."

    def add_arguments(self, parser):
        parser.add_argument("--eleccion", required=True, type=int)
        parser.add_argument("--cantidad", type=int, default=None, help="Cantidad de solicitudes; por defecto, las necesarias para superar la capacidad disponible.")
        parser.add_argument("--aplicar", action="store_true", help="Crear las solicitudes previsualizadas.")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            eleccion = Eleccion.objects.select_for_update().get(pk=options["eleccion"])
        except Eleccion.DoesNotExist:
            raise CommandError("La elección no existe.")
        if eleccion.estado != Eleccion.Estado.PUBLICADA:
            raise CommandError("La elección debe estar publicada.")
        if not solicitudes_cambio_sede_habilitadas(eleccion):
            raise CommandError("El plazo de solicitudes de cambio de sede no está habilitado o ya venció.")
        cantidad = options["cantidad"]
        if cantidad is not None and cantidad < 1:
            raise CommandError("La cantidad debe ser mayor que cero.")
        registros = RegistroPadron.objects.filter(
            eleccion=eleccion, activo=True, solicitudes_cambio_sede__isnull=True,
            asignacion_sede_padron__sede__isnull=False, asignacion_mesa__isnull=False, qr_generado_en__isnull=True,
        ).select_related("asignacion_sede_padron__sede", "eleccion_claustro_departamento__eleccion_claustro").order_by("pk")
        grupos = {}
        for registro in registros:
            alcance = registro.eleccion_claustro_departamento
            origen = registro.asignacion_sede_padron.sede
            for habilitada in alcance.sedes_habilitadas.select_related("sede").filter(sede__activa=True).exclude(sede=origen):
                clave = (alcance.pk, origen.pk, habilitada.sede_id)
                grupos.setdefault(clave, (alcance, origen, habilitada.sede, []))[3].append(registro)
        propuestas = []
        for alcance, origen, destino, electores in grupos.values():
            capacidad = alcance.eleccion_claustro.maximo_votantes_por_mesa
            if not capacidad:
                continue
            mesas = Mesa.objects.filter(eleccion=eleccion, eleccion_claustro_departamento=alcance, sede=destino).annotate(total=Count("asignaciones_padron"))
            huecos = sum(max(0, capacidad - mesa.total) for mesa in mesas)
            necesarias = cantidad if cantidad is not None else huecos + 1
            if len(electores) >= necesarias:
                propuestas.append((necesarias, alcance, origen, destino, electores[:necesarias], huecos))
        if not propuestas:
            raise CommandError("No hay suficientes electores elegibles para ese escenario; probá con --cantidad o revisá las sedes habilitadas.")
        necesarias, alcance, origen, destino, electores, huecos = min(propuestas, key=lambda item: item[0])
        self.stdout.write(f"Elección: {eleccion.nombre}; departamento: {alcance.departamento}; {origen} → {destino}.")
        self.stdout.write(f"Solicitudes: {necesarias}; lugares disponibles en destino: {huecos}.")
        if not options["aplicar"]:
            self.stdout.write("Simulación: no se guardaron solicitudes. Agregá --aplicar para crearlas.")
            return
        solicitudes = [SolicitudCambioSede(registro_padron=r, sede_origen=origen, sede_destino=destino,
                                          observacion="Solicitud generada para prueba de mesas.") for r in electores]
        for solicitud in solicitudes:
            solicitud.full_clean()
        SolicitudCambioSede.objects.bulk_create(solicitudes)
        self.stdout.write(self.style.SUCCESS(f"Se crearon {len(solicitudes)} solicitudes pendientes; no se aprobaron ni modificaron mesas."))
