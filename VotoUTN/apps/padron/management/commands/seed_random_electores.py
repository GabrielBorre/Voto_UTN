import random
import string

from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection
from django.db import transaction

from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron


class Command(BaseCommand):
    help = "Crea electores aleatorios y sus registros en padron/asignacion de mesa."

    def add_arguments(self, parser):
        parser.add_argument("--mesa-id", type=int, default=1, help="ID de la mesa destino.")
        parser.add_argument("--cantidad", type=int, default=15, help="Cantidad de electores a crear.")

    def _generar_legajo(self):
        return "R" + "".join(random.choices(string.digits, k=8))

    def _generar_dni(self):
        return str(random.randint(30000000, 49999999))

    def _generar_nombre(self):
        nombres = [
            "Lucas", "Sofia", "Mateo", "Valentina", "Tomas", "Camila", "Benjamin", "Martina", "Joaquin", "Lucia",
            "Agustin", "Micaela", "Federico", "Julieta", "Nicolas", "Paula", "Franco", "Milagros", "Bruno", "Rocio",
        ]
        apellidos = [
            "Garcia", "Fernandez", "Lopez", "Martinez", "Gonzalez", "Perez", "Rodriguez", "Sanchez", "Romero", "Diaz",
            "Alvarez", "Torres", "Ruiz", "Ramirez", "Flores", "Acosta", "Benitez", "Herrera", "Molina", "Castro",
        ]
        return f"{random.choice(nombres)} {random.choice(apellidos)}"

    def _sincronizar_secuencias(self):
        if connection.vendor != "postgresql":
            return
        sqls = connection.ops.sequence_reset_sql(no_style(), [Elector, RegistroPadron, AsignacionMesa])
        if not sqls:
            return
        with connection.cursor() as cursor:
            for sql in sqls:
                cursor.execute(sql)

    @transaction.atomic
    def handle(self, *args, **options):
        mesa_id = options["mesa_id"]
        cantidad = options["cantidad"]

        if cantidad <= 0:
            raise CommandError("La cantidad debe ser mayor a cero.")

        mesa = Mesa.objects.select_related("eleccion", "eleccion_claustro_departamento", "sede").filter(pk=mesa_id).first()
        if mesa is None:
            raise CommandError(f"No existe la mesa con id {mesa_id}.")
        if mesa.eleccion_claustro_departamento is None:
            raise CommandError("La mesa no tiene configuracion de claustro/departamento y no se puede crear padron.")

        self._sincronizar_secuencias()

        creados = 0

        for _ in range(cantidad):
            for _intento in range(30):
                legajo = self._generar_legajo()
                dni = self._generar_dni()
                if not Elector.objects.filter(legajo=legajo).exists() and not Elector.objects.filter(dni=dni).exists():
                    break
            else:
                raise CommandError("No se pudo generar legajo/dni unicos luego de varios intentos.")

            nombre = self._generar_nombre()
            email = f"{legajo.lower()}@demo.utn.local"

            elector = Elector.objects.create(
                legajo=legajo,
                nombre=nombre,
                dni=dni,
                correo_electronico=email,
            )
            padron = RegistroPadron.objects.create(
                elector=elector,
                eleccion=mesa.eleccion,
                eleccion_claustro_departamento=mesa.eleccion_claustro_departamento,
                sede=mesa.sede,
                activo=True,
            )
            AsignacionMesa.objects.create(registro_padron=padron, mesa=mesa)
            creados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Se crearon {creados} electores con RegistroPadron y AsignacionMesa en la mesa ID {mesa.id}."
            )
        )
