from pathlib import Path
import qrcode
from qrcode.constants import ERROR_CORRECT_L
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image
from apps.elecciones.models import Eleccion, EleccionClaustroDepartamento
from apps.padron.models import RegistroPadron
from apps.asistencia.services import ServicioRegistroParticipacion


class Command(BaseCommand):
    help = "Genera QRs a partir del padron existente y crea hojas de 15 codigos por pagina."
    ROWS_PER_PAGE = 15  # Máximo de filas por hoja
    CELL_WIDTH = 430
    CELL_HEIGHT = 350
    QR_SIZE = 350
    PREFIJO_QR_HOJA = "qr_hoja"

    def add_arguments(self, parser):
        parser.add_argument(
            "--election-id",
            type=int,
            required=True,
            help="ID de la eleccion para asociar mesas y firmar el QR.",
        )
        parser.add_argument("--configuracion-departamento-id", type=int, required=True)
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.BASE_DIR / "generated_qrs",
        )

    def handle(self, *args, **options):
        election_id = options["election_id"]
        configuracion_id = options["configuracion_departamento_id"]
        output = options["output"]
        try:
            eleccion = Eleccion.objects.get(pk=election_id)
        except Eleccion.DoesNotExist as exc:
            raise CommandError(f"No existe la eleccion con id {election_id}.") from exc
        configuracion = EleccionClaustroDepartamento.objects.filter(
            pk=configuracion_id,
            eleccion_claustro__eleccion=eleccion,
        ).first()
        if configuracion is None:
            raise CommandError("La configuración de departamento no pertenece a la elección.")

        registros_qr = []
        qr_images = {}

        padrones = (
            RegistroPadron.objects.select_related("elector", "asignacion_mesa__mesa")
            .filter(
                eleccion=eleccion,
                eleccion_claustro_departamento=configuracion,
                activo=True,
            )
            .order_by("elector__legajo")
        )
        if not padrones.exists():
            raise CommandError("No hay registros de padron activos para esa eleccion/configuracion.")

        for registro_padron in padrones:
            mesa = getattr(getattr(registro_padron, "asignacion_mesa", None), "mesa", None)
            if registro_padron.qr_generado_en and mesa and registro_padron.numero_mesa_qr != mesa.numero:
                raise CommandError(
                    f"El QR del legajo {registro_padron.elector.legajo} fue emitido para la mesa "
                    f"{registro_padron.numero_mesa_qr}; no puede regenerarse para la mesa {mesa.numero}."
                )

        output.mkdir(parents=True, exist_ok=True)
        for png_existente in output.glob("*.png"):
            png_existente.unlink(missing_ok=True)

        padrones_sin_mesa = 0
        for registro_padron in padrones:
            mesa = getattr(getattr(registro_padron, "asignacion_mesa", None), "mesa", None)
            if mesa is None:
                padrones_sin_mesa += 1
                continue

            payload = ServicioRegistroParticipacion.generar_codigo_qr(
                eleccion_id=eleccion.id,
                mesa_numero=mesa.numero,
                identificador_qr=registro_padron.identificador_qr,
            )
            qr = self.generar_qr(payload)
            legajo = registro_padron.elector.legajo
            qr_images[legajo] = qr
            qr.save(output / f"mesa_{mesa.numero}_legajo_{legajo}.png")
            registros_qr.append((registro_padron.elector, mesa.numero, registro_padron.pk))

        if not registros_qr:
            raise CommandError("No se pudo generar ningun QR: todos los padrones quedaron sin mesa asignada.")

        # Generar las hojas de a 15 votantes
        hojas_creadas = self.crear_hojas(registros_qr, qr_images, output)

        momento_emision = timezone.now()
        with transaction.atomic():
            for _, mesa_numero, registro_id in registros_qr:
                RegistroPadron.objects.filter(pk=registro_id, qr_generado_en__isnull=True).update(
                    qr_generado_en=momento_emision,
                    numero_mesa_qr=mesa_numero,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(registros_qr)} electores procesados para la eleccion {eleccion.id}. "
                f"Padrones sin mesa: {padrones_sin_mesa}. "
                f"Se crearon {hojas_creadas} hoja(s) de QR."
            )
        )

    def generar_qr(self, value):
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=12,
            border=4,
        )
        qr.add_data(value)
        qr.make(fit=False)

        image = qr.make_image(
            fill_color="black",
            back_color="white"
        ).convert("RGB")
        
        return image.resize(
            (self.QR_SIZE, self.QR_SIZE),
            Image.Resampling.NEAREST
        )

    def crear_hojas(self, registros_qr, qr_images, output_dir):
        """
        Genera hojas separadas por mesa, en bloques de 15 por página.
        """
        total_hojas = 0

        registros_ordenados = sorted(registros_qr, key=lambda item: (item[1], item[0].legajo))
        por_mesa = {}
        for elector, mesa_numero, _ in registros_ordenados:
            por_mesa.setdefault(mesa_numero, []).append(elector)

        for mesa_numero, electores_mesa in por_mesa.items():
            for i in range(0, len(electores_mesa), self.ROWS_PER_PAGE):
                lote_votantes = electores_mesa[i : i + self.ROWS_PER_PAGE]
                page_number = (i // self.ROWS_PER_PAGE) + 1

                sheet = Image.new(
                    "RGB",
                    (
                        self.CELL_WIDTH,
                        self.CELL_HEIGHT * len(lote_votantes),
                    ),
                    "white",
                )

                for row, voter in enumerate(lote_votantes):
                    y = row * self.CELL_HEIGHT
                    qr = qr_images[voter.legajo]
                    x = (self.CELL_WIDTH - self.QR_SIZE) // 2
                    qr_y = y + 20
                    sheet.paste(qr, (x, qr_y))

                destination = output_dir / f"{self.PREFIJO_QR_HOJA}_mesa_{mesa_numero}_pagina_{page_number}.png"
                sheet.save(destination)
                total_hojas += 1

        return total_hojas
