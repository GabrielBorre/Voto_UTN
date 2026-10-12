from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.asistencia.models import RegistroParticipacion
from apps.elecciones.models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionClaustroTurno,
    EleccionSede,
)
from apps.mesas.models import AsignacionMesa, Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede, Turno


class Command(BaseCommand):
    help = "Carga de forma idempotente una eleccion cerrada completa para verificacion."

    @transaction.atomic
    def handle(self, *args, **options):
        fecha_inicio = date(2024, 3, 15)
        fecha_fin = date(2024, 11, 20)
        nombre_eleccion = "Eleccion 2024 demo"
        eleccion, creada = Eleccion.objects.get_or_create(
            nombre=nombre_eleccion,
            defaults={
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
                "estado": Eleccion.Estado.CERRADA,
                "habilitada": False,
            },
        )
        if not creada:
            eleccion.nombre = nombre_eleccion
            eleccion.fecha_inicio = fecha_inicio
            eleccion.fecha_fin = fecha_fin
            eleccion.estado = Eleccion.Estado.CERRADA
            eleccion.habilitada = False
            eleccion.save(
                update_fields=(
                    "nombre",
                    "fecha_inicio",
                    "fecha_fin",
                    "estado",
                    "habilitada",
                )
            )

        sede, _ = Sede.objects.get_or_create(nombre="Sede de verificacion")
        claustro, _ = Claustro.objects.get_or_create(nombre="Claustro de verificacion")
        departamento = Departamento.objects.filter(codigo="VER-CERRADA").first()
        if departamento and departamento.nombre != "Departamento de verificacion":
            raise CommandError("El codigo VER-CERRADA ya pertenece a otro departamento.")
        if departamento is None:
            departamento = Departamento.objects.filter(nombre="Departamento de verificacion").first()
            if departamento and departamento.codigo != "VER-CERRADA":
                raise CommandError("El nombre del departamento de verificacion ya esta en uso.")
            if departamento is None:
                departamento = Departamento.objects.create(
                    nombre="Departamento de verificacion",
                    codigo="VER-CERRADA",
                )
        turno, _ = Turno.objects.get_or_create(
            nombre="Turno de verificacion",
            defaults={"hora_inicio": "08:00", "hora_fin": "12:00"},
        )

        EleccionSede.objects.get_or_create(eleccion=eleccion, sede=sede)
        eleccion_claustro, _ = EleccionClaustro.objects.get_or_create(
            eleccion=eleccion,
            claustro=claustro,
            defaults={
                "fecha_votacion": fecha_fin,
                "organizacion_departamentos": claustro.organizacion_departamentos,
            },
        )
        if eleccion_claustro.fecha_votacion != fecha_fin:
            eleccion_claustro.fecha_votacion = fecha_fin
            eleccion_claustro.save(update_fields=("fecha_votacion",))
        EleccionClaustroTurno.objects.get_or_create(
            eleccion_claustro=eleccion_claustro,
            turno=turno,
        )
        EleccionClaustroSede.objects.get_or_create(
            eleccion_claustro=eleccion_claustro,
            sede=sede,
        )
        alcance, _ = EleccionClaustroDepartamento.objects.get_or_create(
            eleccion_claustro=eleccion_claustro,
            departamento=departamento,
        )
        EleccionClaustroDepartamentoSede.objects.get_or_create(
            eleccion_claustro_departamento=alcance,
            sede=sede,
        )
        mesa, _ = Mesa.objects.get_or_create(
            eleccion=eleccion,
            numero=1,
            defaults={
                "eleccion_claustro_departamento": alcance,
                "sede": sede,
            },
        )
        if mesa.eleccion_claustro_departamento_id != alcance.pk or mesa.sede_id != sede.pk:
            raise CommandError("La mesa 1 existente no coincide con el alcance de la eleccion demo.")

        elector = Elector.objects.filter(dni="38999222").first()
        if elector is None:
            if Elector.objects.filter(legajo="SEED-38999222").exists():
                raise CommandError("El legajo SEED-38999222 ya pertenece a otro elector.")
            elector = Elector.objects.create(
                legajo="SEED-38999222",
                nombre="Elector de prueba",
                apellido="Verificacion",
                dni="38999222",
            )
        elif Elector.objects.filter(legajo="SEED-38999222").exclude(pk=elector.pk).exists():
            raise CommandError("El legajo SEED-38999222 ya pertenece a otro elector.")

        registro_padron, _ = RegistroPadron.objects.get_or_create(
            elector=elector,
            eleccion=eleccion,
            defaults={
                "eleccion_claustro_departamento": alcance,
                "sede": sede,
                "activo": True,
            },
        )
        if registro_padron.eleccion_claustro_departamento_id != alcance.pk:
            raise CommandError("El elector solicitado ya tiene otro alcance en la eleccion demo.")
        asignacion, _ = AsignacionMesa.objects.get_or_create(
            registro_padron=registro_padron,
            defaults={"mesa": mesa},
        )
        if asignacion.mesa_id != mesa.pk:
            raise CommandError("El elector solicitado ya esta asignado a otra mesa.")

        usuario_modelo = get_user_model()
        registrador, creado = usuario_modelo.objects.get_or_create(
            username="semilla_eleccion_cerrada",
            defaults={"is_active": False},
        )
        if creado:
            registrador.set_unusable_password()
            registrador.save(update_fields=("password",))
        participacion, _ = RegistroParticipacion.objects.get_or_create(
            registro_padron=registro_padron,
            defaults={
                "mesa": mesa,
                "registrada_por": registrador,
                "metodo": RegistroParticipacion.Metodo.MANUAL,
            },
        )
        if participacion.mesa_id != mesa.pk:
            raise CommandError("La participacion existente no corresponde a la mesa de la eleccion demo.")

        self.stdout.write(
            self.style.SUCCESS(
                f'Eleccion "{eleccion.nombre}" lista: cerrada, 1 elector en el padron, '
                "1 mesa y participacion registrada para el DNI 38999222."
            )
        )
