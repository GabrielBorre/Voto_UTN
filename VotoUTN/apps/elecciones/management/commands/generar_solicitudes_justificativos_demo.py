import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Exists, OuterRef

from apps.asistencia.models import RegistroParticipacion
from apps.autoridades.models import AsignacionAutoridad
from apps.elecciones.models import Eleccion, EleccionClaustroDepartamentoSede
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import RegistroPadron, SolicitudCambioSede
from apps.padron.services import eleccion_tiene_padron_emitido


TIPOS_JUSTIFICATIVO = ("Certificado medico", "Viaje", "Razones laborales", "Fuerza mayor")

OBSERVACIONES_CAMBIO_SEDE = (
    "Me mudé y la otra sede me queda más cerca.",
    "Curso la mayoría de las materias en la sede solicitada.",
    "Por razones laborales me resulta más accesible la sede solicitada.",
    "Solicito el cambio por cercanía a mi domicilio.",
    "",
)

DETALLES_ELECTOR = (
    "Me encontraba enfermo el día de la votación, adjunto certificado.",
    "Estaba de viaje fuera de la ciudad por motivos familiares.",
    "Tuve un turno laboral que no pude reprogramar.",
    "Tuve un inconveniente de transporte que me impidió llegar.",
)

DETALLES_AUTORIDAD = (
    "No pude presentarme como autoridad de mesa por razones de salud.",
    "Tuve un compromiso laboral impostergable el día de la elección.",
    "Un problema familiar me impidió asistir a la mesa asignada.",
)


class Command(BaseCommand):
    help = (
        "Genera solicitudes de cambio de sede y justificativos de inasistencia de demo "
        "sobre el padrón de la elección actual (publicada o en curso)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--solicitudes", type=int, default=60)
        parser.add_argument("--justificativos-electores", type=int, default=7)
        parser.add_argument("--justificativos-autoridades", type=int, default=3)
        parser.add_argument("--semilla", type=int, default=None, help="Semilla aleatoria para resultados reproducibles.")

    @transaction.atomic
    def handle(self, *args, **options):
        for opcion in ("solicitudes", "justificativos_electores", "justificativos_autoridades"):
            if options[opcion] < 0:
                raise CommandError(f"--{opcion.replace('_', '-')} no puede ser negativo.")
        aleatorio = random.Random(options["semilla"])

        eleccion = Eleccion.objects.filter(
            estado__in=(Eleccion.Estado.PUBLICADA, Eleccion.Estado.EN_CURSO),
        ).first()
        if eleccion is None:
            raise CommandError("No existe una elección publicada o en curso.")
        self.stdout.write(f"Elección: {eleccion.nombre} ({eleccion.get_estado_display()})")

        if eleccion_tiene_padron_emitido(eleccion):
            self.stdout.write(self.style.WARNING(
                "El padrón imprimible ya fue emitido: las solicitudes de cambio de sede quedarán en modo lectura."
            ))

        registros = RegistroPadron.objects.filter(eleccion=eleccion, activo=True)
        solicitudes = self._generar_solicitudes(registros, options["solicitudes"], aleatorio)
        tipos = self._tipos_justificativo()
        autoridades = self._generar_justificativos_autoridades(
            registros, options["justificativos_autoridades"], tipos, aleatorio,
        )
        electores = self._generar_justificativos_electores(
            registros, options["justificativos_electores"], tipos, aleatorio,
        )

        self.stdout.write(self.style.SUCCESS(
            f"Creadas {solicitudes} solicitudes de cambio de sede, "
            f"{electores} justificativos de electores y {autoridades} de autoridades de mesa."
        ))

    def _advertir_faltante(self, descripcion, pedidos, creados):
        if creados < pedidos:
            self.stdout.write(self.style.WARNING(
                f"Solo se pudieron crear {creados} de {pedidos} {descripcion} (no hay más candidatos válidos)."
            ))

    def _generar_solicitudes(self, registros, cantidad, aleatorio):
        if cantidad == 0:
            return 0
        sedes_por_alcance = {}
        for alcance_id, sede_id in EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento__in=registros.values("eleccion_claustro_departamento"),
            sede__activa=True,
        ).values_list("eleccion_claustro_departamento_id", "sede_id"):
            sedes_por_alcance.setdefault(alcance_id, set()).add(sede_id)

        # Igual que el formulario del elector: una sola solicitud por elección y sede de origen definida.
        candidatos = [
            registro
            for registro in registros.filter(sede__isnull=False)
            .exclude(solicitudes_cambio_sede__isnull=False)
            .select_related("eleccion_claustro_departamento")
            if sedes_por_alcance.get(registro.eleccion_claustro_departamento_id, set()) - {registro.sede_id}
        ]
        aleatorio.shuffle(candidatos)

        creadas = 0
        for registro in candidatos[:cantidad]:
            destinos = sorted(sedes_por_alcance[registro.eleccion_claustro_departamento_id] - {registro.sede_id})
            solicitud = SolicitudCambioSede(
                registro_padron=registro,
                sede_origen_id=registro.sede_id,
                sede_destino_id=aleatorio.choice(destinos),
                estado=SolicitudCambioSede.Estado.PENDIENTE,
                observacion=aleatorio.choice(OBSERVACIONES_CAMBIO_SEDE),
            )
            solicitud.full_clean()
            solicitud.save()
            creadas += 1
        self._advertir_faltante("solicitudes de cambio de sede", cantidad, creadas)
        return creadas

    def _tipos_justificativo(self):
        tipos = list(TipoJustificativo.objects.filter(activo=True))
        if not tipos:
            tipos = [
                TipoJustificativo.objects.get_or_create(nombre=nombre, defaults={"activo": True})[0]
                for nombre in TIPOS_JUSTIFICATIVO
            ]
        return tipos

    def _crear_justificativos(self, candidatos, cantidad, ausencia, detalles, tipos, aleatorio):
        candidatos = list(candidatos)
        aleatorio.shuffle(candidatos)
        creados = 0
        for registro in candidatos[:cantidad]:
            justificativo = JustificativoAusencia(
                registro_padron=registro,
                ausencia=ausencia,
                tipo=aleatorio.choice(tipos),
                detalle=aleatorio.choice(detalles),
                estado=JustificativoAusencia.Estado.PENDIENTE,
            )
            justificativo.full_clean()
            justificativo.save()
            creados += 1
        return creados

    def _generar_justificativos_autoridades(self, registros, cantidad, tipos, aleatorio):
        if cantidad == 0:
            return 0
        candidatos = registros.filter(asignacion_autoridad__isnull=False).exclude(
            justificativos__ausencia=JustificativoAusencia.Ausencia.AUTORIDAD,
        )
        creados = self._crear_justificativos(
            candidatos, cantidad, JustificativoAusencia.Ausencia.AUTORIDAD, DETALLES_AUTORIDAD, tipos, aleatorio,
        )
        self._advertir_faltante("justificativos de autoridades de mesa", cantidad, creados)
        return creados

    def _generar_justificativos_electores(self, registros, cantidad, tipos, aleatorio):
        if cantidad == 0:
            return 0
        candidatos = (
            registros.annotate(
                es_autoridad=Exists(AsignacionAutoridad.objects.filter(registro_padron=OuterRef("pk"))),
                participo=Exists(RegistroParticipacion.objects.filter(registro_padron=OuterRef("pk"))),
            )
            .filter(es_autoridad=False, participo=False)
            .exclude(justificativos__ausencia=JustificativoAusencia.Ausencia.VOTAR)
        )
        creados = self._crear_justificativos(
            candidatos, cantidad, JustificativoAusencia.Ausencia.VOTAR, DETALLES_ELECTOR, tipos, aleatorio,
        )
        self._advertir_faltante("justificativos de electores", cantidad, creados)
        return creados
