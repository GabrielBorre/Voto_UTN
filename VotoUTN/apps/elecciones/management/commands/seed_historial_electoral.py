from datetime import date, datetime, time, timedelta

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
    EleccionSede,
)
from apps.elecciones.historial_electores import construir_historial_electoral
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.mesas.models import Mesa
from apps.padron.models import Elector, RegistroPadron
from apps.parametros.models import Claustro, Departamento, Sede


class Command(BaseCommand):
    help = (
        "Carga seis elecciones historicas de demostracion para un DNI, "
        "sin modificar elecciones existentes ni crear una eleccion abierta."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dni", required=True, help="DNI del elector existente")

    @transaction.atomic
    def handle(self, *args, **options):
        dni = options["dni"]
        elector = Elector.objects.select_for_update().filter(dni=dni).first()
        if elector is None:
            raise CommandError(f"No existe un elector con DNI {dni}; no se creo ningun dato.")

        claustro = Claustro.objects.filter(nombre="Estudiantes", activo=True).first()
        if claustro is None:
            raise CommandError("No existe un claustro activo 'Estudiantes'.")
        departamento = self._obtener_departamento(elector)
        sede = self._obtener_sede(elector)
        if departamento is None:
            raise CommandError(
                "No se encontro un departamento activo asociado al elector ni en sus padrones."
            )
        if sede is None:
            raise CommandError("No existe una sede activa para configurar las elecciones demo.")

        registrador = self._obtener_registrador()
        tipo_justificativo = TipoJustificativo.objects.filter(activo=True).order_by("pk").first()
        if tipo_justificativo is None:
            tipo_justificativo, _ = TipoJustificativo.objects.get_or_create(
                nombre="Justificativo de demostracion"
            )

        hoy = timezone.localdate()
        escenarios = self._escenarios(hoy)
        elecciones_demo = []
        for escenario in escenarios:
            eleccion, alcance, mesa = self._obtener_configuracion(
                escenario,
                claustro,
                departamento,
                sede,
            )
            registro_padron = self._obtener_registro_padron(elector, eleccion, alcance, sede)
            estado = self._crear_estado(
                escenario,
                registro_padron,
                mesa,
                registrador,
                tipo_justificativo,
            )
            elecciones_demo.append(eleccion)

        estado_por_eleccion = {
            item["eleccion"].pk: item["estado"]
            for item in construir_historial_electoral(elector)
        }
        estados = [
            (eleccion.nombre, estado_por_eleccion[eleccion.pk])
            for eleccion in elecciones_demo
        ]

        self.stdout.write(
            self.style.SUCCESS(
                f"Historial demo listo para el DNI {dni}: "
                f"{len(estados)} elecciones cerradas, sin duplicar registros."
            )
        )
        for nombre, estado in estados:
            self.stdout.write(f"- {nombre}: {estado}")

    def _escenarios(self, hoy):
        return (
            {
                "clave": "Voto Emitido",
                "fecha_fin": date(hoy.year - 5, 6, 15),
                "estado": "Voto Emitido",
                "participacion": False,
            },
            {
                "clave": "Infractor",
                "fecha_fin": date(hoy.year - 4, 6, 15),
                "estado": "Infractor",
                "participacion": True,
            },
            {
                "clave": "Pendiente de Revision",
                "fecha_fin": date(hoy.year - 3, 6, 15),
                "estado": JustificativoAusencia.Estado.PENDIENTE,
                "participacion": True,
            },
            {
                "clave": "Inasistencia Justificada",
                "fecha_fin": date(hoy.year - 2, 6, 15),
                "estado": JustificativoAusencia.Estado.APROBADO,
                "participacion": True,
            },
            {
                "clave": "Infractor - Justificacion Rechazada",
                "fecha_fin": date(hoy.year - 1, 6, 15),
                "estado": JustificativoAusencia.Estado.RECHAZADO,
                "participacion": True,
            },
            {
                "clave": "En Curso - Voto No Registrado",
                "fecha_fin": date(hoy.year, 6, 15)
                if date(hoy.year, 6, 15) < hoy
                else date(hoy.year - 1, 6, 15),
                "estado": "En Curso - Voto No Registrado",
                "participacion": True,
                "periodo_vigente": True,
            },
        )

    def _obtener_departamento(self, elector):
        if elector.departamento_principal_id and elector.departamento_principal.activo:
            return elector.departamento_principal
        registro_previo = (
            RegistroPadron.objects.filter(
                elector=elector,
                eleccion_claustro_departamento__departamento__isnull=False,
                eleccion_claustro_departamento__departamento__activo=True,
            )
            .select_related("eleccion_claustro_departamento__departamento")
            .order_by("-eleccion__fecha_inicio", "-pk")
            .first()
        )
        return (
            registro_previo.eleccion_claustro_departamento.departamento
            if registro_previo
            else None
        )

    def _obtener_sede(self, elector):
        registro_previo = (
            RegistroPadron.objects.filter(elector=elector, sede__activa=True)
            .select_related("sede")
            .order_by("-eleccion__fecha_inicio", "-pk")
            .first()
        )
        return (
            registro_previo.sede
            if registro_previo
            else Sede.objects.filter(activa=True).order_by("pk").first()
        )

    def _obtener_registrador(self):
        usuario, creado = get_user_model().objects.get_or_create(
            username="semilla_historial_electoral",
            defaults={"is_active": False},
        )
        if usuario.is_active:
            raise CommandError(
                "El usuario semilla_historial_electoral ya existe y esta activo; "
                "no se lo usara como registrador."
            )
        if creado:
            usuario.set_unusable_password()
            usuario.save(update_fields=("password",))
        return usuario

    def _obtener_configuracion(self, escenario, claustro, departamento, sede):
        fecha_fin = escenario["fecha_fin"]
        fecha_inicio = fecha_fin - timedelta(days=30)
        fecha_limite = (
            fecha_fin + timedelta(days=180)
            if escenario.get("periodo_vigente")
            else fecha_fin + timedelta(days=30)
        )
        nombre = f"[DEMO] Historial electoral {fecha_fin.year} - {escenario['clave']}"
        eleccion, _ = Eleccion.objects.get_or_create(
            nombre=nombre,
            defaults={
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
                "fecha_limite_justificacion_electores": fecha_limite,
                "justificacion_electores_habilitada_en": self._instante_habilitacion(fecha_fin),
                "estado": Eleccion.Estado.FINALIZADA,
                "habilitada": False,
            },
        )
        if eleccion.estado != Eleccion.Estado.FINALIZADA or eleccion.habilitada:
            raise CommandError(f'La eleccion existente "{nombre}" no es una eleccion demo cerrada.')
        if (
            eleccion.fecha_limite_justificacion_electores != fecha_limite
            and not escenario.get("periodo_vigente")
        ):
            raise CommandError(
                f'La eleccion existente "{nombre}" tiene un plazo distinto; no se modifico.'
            )
        if eleccion.justificacion_electores_habilitada_en is None:
            eleccion.justificacion_electores_habilitada_en = self._instante_habilitacion(fecha_fin)
            eleccion.save(update_fields=("justificacion_electores_habilitada_en",))

        EleccionSede.objects.get_or_create(eleccion=eleccion, sede=sede)
        eleccion_claustro, _ = EleccionClaustro.objects.get_or_create(
            eleccion=eleccion,
            claustro=claustro,
            defaults={
                "fecha_votacion": fecha_fin,
                "organizacion_departamentos": claustro.organizacion_departamentos,
            },
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
        if (
            mesa.eleccion_claustro_departamento_id != alcance.pk
            or mesa.sede_id != sede.pk
        ):
            raise CommandError(f'La mesa de "{nombre}" tiene un alcance distinto; no se modifico.')
        return eleccion, alcance, mesa

    def _obtener_registro_padron(self, elector, eleccion, alcance, sede):
        registro, _ = RegistroPadron.objects.get_or_create(
            elector=elector,
            eleccion=eleccion,
            defaults={
                "eleccion_claustro_departamento": alcance,
                "sede": sede,
                "activo": True,
            },
        )
        if registro.eleccion_claustro_departamento_id != alcance.pk or registro.sede_id != sede.pk:
            raise CommandError(
                f'El padron de "{eleccion.nombre}" ya tiene un alcance diferente; no se modifico.'
            )
        return registro

    def _crear_estado(self, escenario, registro, mesa, registrador, tipo_justificativo):
        justificaciones = JustificativoAusencia.objects.filter(
            registro_padron=registro,
            ausencia=JustificativoAusencia.Ausencia.VOTAR,
        )
        participacion = RegistroParticipacion.objects.filter(registro_padron=registro).first()
        estado_esperado = escenario["estado"]
        tiene_participacion = escenario["participacion"]
        if tiene_participacion:
            participacion, _ = RegistroParticipacion.objects.get_or_create(
                registro_padron=registro,
                defaults={
                    "mesa": mesa,
                    "registrada_por": registrador,
                    "metodo": RegistroParticipacion.Metodo.MANUAL,
                },
            )
            if participacion.mesa_id != mesa.pk:
                raise CommandError(
                    f'La participacion de "{registro.eleccion.nombre}" pertenece a otra mesa.'
                )
        elif participacion is not None or justificaciones.exists():
            raise CommandError(
                f'El registro de "{registro.eleccion.nombre}" ya tiene una ausencia registrada.'
            )

        if estado_esperado in {
            JustificativoAusencia.Estado.PENDIENTE,
            JustificativoAusencia.Estado.APROBADO,
            JustificativoAusencia.Estado.RECHAZADO,
        }:
            justificativo, creado = JustificativoAusencia.objects.get_or_create(
                registro_padron=registro,
                ausencia=JustificativoAusencia.Ausencia.VOTAR,
                defaults={
                    "tipo": tipo_justificativo,
                    "detalle": "Registro de demostracion para visualizar el historial electoral.",
                    "estado": estado_esperado,
                    "resuelta_por": (
                        None if estado_esperado == JustificativoAusencia.Estado.PENDIENTE else registrador
                    ),
                    "resuelta_en": (
                        None
                        if estado_esperado == JustificativoAusencia.Estado.PENDIENTE
                        else self._instante_habilitacion(registro.eleccion.fecha_fin)
                        + timedelta(days=2)
                    ),
                    "observacion_resolucion": (
                        ""
                        if estado_esperado == JustificativoAusencia.Estado.PENDIENTE
                        else "Resolucion de demostracion."
                    ),
                },
            )
            if not creado and justificativo.estado != estado_esperado:
                raise CommandError(
                    f'El justificativo de "{registro.eleccion.nombre}" tiene otro estado.'
                )
            if creado:
                justificativo.presentada_en = self._instante_habilitacion(
                    registro.eleccion.fecha_fin
                ) + timedelta(days=1)
                justificativo.save(update_fields=("presentada_en",))
            return

        if justificaciones.exists():
            raise CommandError(
                f'El registro de "{registro.eleccion.nombre}" ya tiene un justificativo.'
            )

    def _instante_habilitacion(self, fecha_fin):
        fecha_habilitacion = fecha_fin + timedelta(days=1)
        return timezone.make_aware(
            datetime.combine(fecha_habilitacion, time.min),
            timezone.get_current_timezone(),
        )
