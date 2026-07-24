from pathlib import Path
import qrcode
from qrcode.constants import ERROR_CORRECT_M
from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image
from apps.elections.models import Voter

VOTERS = [
    ("203425", "Nicolas Calle", "40123456"),
    ("203426", "Juan Perez", "40234567"),
    ("203427", "Lucia Gomez", "41123456"),
    ("203428", "Martina Rodriguez", "41234567"),
    ("203429", "Santiago Fernandez", "41345678"),
    ("203430", "Valentina Lopez", "41456789"),
    ("203431", "Mateo Martinez", "41567890"),
    ("203432", "Camila Sanchez", "41678901"),
    ("203433", "Tomas Gonzalez", "41789012"),
    ("203434", "Sofia Romero", "41890123"),
    ("203435", "Franco Diaz", "41901234"),
    ("203436", "Agustina Torres", "42012345"),
    ("203437", "Bruno Alvarez", "42123456"),
    ("203438", "Julieta Castro", "42234567"),
    ("203439", "Lautaro Ruiz", "42345678"),
]

class Command(BaseCommand):
    help = "Genera electores de prueba y una hoja QR optimizada para escaneo."
    ROWS = 15
    CELL_WIDTH = 430
    CELL_HEIGHT = 350
    QR_SIZE = 350
    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            default=settings.BASE_DIR / "generated_qrs",
        )
    def handle(self, *args, **options):
        output = options["output"]
        output.mkdir(parents=True, exist_ok=True)
        voters = []
        qr_images = {}
        for legajo, name, dni in VOTERS:
            voter, _ = Voter.objects.update_or_create(
                legajo=legajo,
                defaults={
                    "name": name,
                    "dni": dni,
                }
            )
            voters.append(voter)
            qr = self.generate_qr(voter.legajo)
            qr_images[voter.legajo] = qr
            qr.save(output / f"{voter.legajo}.png")
        self.create_sheet(
            voters,
            qr_images,
            output / "hoja_qr.png"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(voters)} electores generados."
            )
        )
    def generate_qr(self, value):
        qr = qrcode.QRCode(
            version=2,
            error_correction=ERROR_CORRECT_M,
            box_size=12,
            border=4,
        )
        qr.add_data(f"VOTER:{value}")
        qr.make(fit=False)
        image = qr.make_image(
            fill_color="black",
            back_color="white"
        ).convert("RGB")
        image = image.resize(
            (self.QR_SIZE, self.QR_SIZE),
            Image.Resampling.NEAREST
        )
        return image
    def create_sheet(
        self,
        voters,
        qr_images,
        destination,
    ):
        sheet = Image.new(
            "RGB",
            (
                self.CELL_WIDTH,
                self.CELL_HEIGHT * self.ROWS,
            ),
            "white",
        )
        for row, voter in enumerate(voters):
            y = row * self.CELL_HEIGHT
            qr = qr_images[voter.legajo]
            x = (self.CELL_WIDTH - self.QR_SIZE) // 2
            qr_y = y + 20
            sheet.paste(
                qr,
                (x, qr_y)
            )
        sheet.save(destination)