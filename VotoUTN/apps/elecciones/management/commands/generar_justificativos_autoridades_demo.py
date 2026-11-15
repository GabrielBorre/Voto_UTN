from apps.elecciones.demo_comandos import ComandoJustificativosDemo
from apps.justificativos.models import JustificativoAusencia


class Command(ComandoJustificativosDemo):
    help = "Genera justificativos de demo para autoridades de mesa asignadas."
    ausencia = JustificativoAusencia.Ausencia.AUTORIDAD
