from apps.elecciones.demo_comandos import ComandoJustificativosDemo
from apps.justificativos.models import JustificativoAusencia


class Command(ComandoJustificativosDemo):
    help = "Genera justificativos de demo para electores con ausencia registrada."
    ausencia = JustificativoAusencia.Ausencia.VOTAR
