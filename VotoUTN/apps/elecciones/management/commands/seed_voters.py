from pathlib import Path
import base64
import struct
import hashlib
import hmac
import qrcode
from qrcode.constants import ERROR_CORRECT_L
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image
from apps.elecciones.models import Eleccion, Elector, Mesa

VOTERS = [
    ("203425", "Nicolas Calle", "40123456", 15),
    ("203426", "Juan Perez", "40234567", 15),
    ("203427", "Lucia Gomez", "41123456", 15),
    ("203428", "Martina Rodriguez", "41234567", 15),
    ("203429", "Santiago Fernandez", "41345678", 15),
    ("203430", "Valentina Lopez", "41456789", 15),
    ("203431", "Mateo Martinez", "41567890", 15),
    ("203432", "Camila Sanchez", "41678901", 15),
    ("203433", "Tomas Gonzalez", "41789012", 15),
    ("203434", "Sofia Romero", "41890123", 15),
    ("203435", "Franco Diaz", "41901234", 15),
    ("203436", "Agustina Torres", "42012345", 15),
    ("203437", "Bruno Alvarez", "42123456", 15),
    ("203438", "Julieta Castro", "42234567", 15),
    ("203439", "Lautaro Ruiz", "42345678", 15),
    ("203440", "Nicolas Calle", "40123478", 15),
    ("203441", "Juan Perez", "40234127", 15),
    ("203442", "Lucia Gomez", "41123412", 15),
    ("203443", "Martina Rodriguez", "41234512", 15),
    ("203444", "Santiago Fernandez", "41345634", 15),
    ("203445", "Valentina Lopez", "41456759", 15),
    ("203446", "Mateo Martinez", "41563290", 15),
    ("203447", "Camila Sanchez", "41674301", 15),
    ("203448", "Tomas Gonzalez", "41789542", 15),
    ("203449", "Sofia Romero", "41890543", 15),
    ("203450", "Franco Diaz", "41901344", 15),
    ("203451", "Agustina Torres", "42012341", 15),
    ("203452", "Bruno Alvarez", "42123436", 15),
    ("203453", "Julieta Castro", "42234557", 15),
    ("203454", "Lautaro Ruiz", "42345668", 15),
    ("203440", "Sofia Romero", "41891243", 16),
    ("201250", "Franco Diaz", "41901124", 16),
    ("203251", "Agustina Torres", "42322341", 16),
    ("203122", "Bruno Alvarez", "42121436", 16),
    ("203123", "Julieta Castro", "42434557", 16),
    ("203124", "Lautaro Ruiz", "4234368", 16),
]


class Command(BaseCommand):
    help = "Genera electores de prueba y hojas QR optimizadas divididas cada 15 votantes."
    ROWS_PER_PAGE = 15  # Máximo de filas por hoja
    CELL_WIDTH = 430
    CELL_HEIGHT = 350
    QR_SIZE = 350

    def add_arguments(self, parser):
        parser.add_argument(
            "--election-id",
            type=int,
            required=True,
            help="ID de la eleccion para asociar mesas y firmar el QR.",
        )
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.BASE_DIR / "generated_qrs",
        )

    def handle(self, *args, **options):
        election_id = options["election_id"]
        output = options["output"]
        try:
            eleccion = Eleccion.objects.get(pk=election_id)
        except Eleccion.DoesNotExist as exc:
            raise CommandError(f"No existe la eleccion con id {election_id}.") from exc

        output.mkdir(parents=True, exist_ok=True)
        voters = []
        qr_images = {}
        mesas_by_numero = {}

        for legajo, nombre, dni, mesa_numero in VOTERS:
            mesa = mesas_by_numero.get(mesa_numero)
            if mesa is None:
                mesa, _ = Mesa.objects.get_or_create(eleccion=eleccion, numero=mesa_numero)
                mesas_by_numero[mesa_numero] = mesa

            elector, _ = Elector.objects.update_or_create(
                legajo=legajo,
                defaults={
                    "nombre": nombre,
                    "dni": dni,
                    "mesa": mesa,
                },
            )
            voters.append(elector)
            payload = self.generar_payload_firmado(
                eleccion_id=eleccion.id,
                mesa_numero=mesa.numero,
                legajo=elector.legajo,
            )
            qr = self.generar_qr(payload)
            qr_images[elector.legajo] = qr
            qr.save(output / f"{elector.legajo}.png")

        # Generar las hojas de a 15 votantes
        hojas_creadas = self.crear_hojas(voters, qr_images, output)

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(voters)} electores generados para la eleccion {eleccion.id}. "
                f"Se crearon {hojas_creadas} hoja(s) de QR."
            )
        )

    def generar_payload_firmado(self, *, eleccion_id, mesa_numero, legajo):
        legajo_int = int(legajo)

        # 1. Datos binarios (8 bytes)
        data_bytes = struct.pack(">HHI", eleccion_id, mesa_numero, legajo_int)

        # 2. Firma HMAC (4 bytes)
        sig = hmac.new(
            settings.CLAVE_FIRMA_QR.encode("utf-8"),
            data_bytes,
            hashlib.sha256
        ).digest()[:4]

        # 3. Base64 URL-safe (16 caracteres)
        payload_bin = data_bytes + sig
        return base64.urlsafe_b64encode(payload_bin).decode("ascii").rstrip("=")

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

    def crear_hojas(self, voters, qr_images, output_dir):
        """
        Divide el listado total de votantes en bloques de 15 y genera
        un archivo PNG por cada página ('hoja_qr_1.png', 'hoja_qr_2.png', etc.).
        """
        # Agrupar votantes en lotes de a 15
        total_hojas = 0
        
        for i in range(0, len(voters), self.ROWS_PER_PAGE):
            lote_votantes = voters[i : i + self.ROWS_PER_PAGE]
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

            destination = output_dir / f"hoja_qr_{page_number}.png"
            sheet.save(destination)
            total_hojas += 1

        return total_hojas
