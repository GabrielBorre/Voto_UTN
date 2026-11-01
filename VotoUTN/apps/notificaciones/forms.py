from uuid import uuid4

from django import forms

from apps.elecciones.models import Eleccion
from apps.notificaciones.models import (
    ComunicacionFechaAdministrativa,
    PlantillaNotificacion,
    VarianteComunicacionFechaAdministrativa,
)
from apps.parametros.models import Claustro, FechaAdministrativa


class FormularioPlantillaNotificacion(forms.ModelForm):
    roles_destinatarios = forms.MultipleChoiceField(choices=FechaAdministrativa.RolDestinatario.choices, widget=forms.CheckboxSelectMultiple)
    claustros = forms.ModelMultipleChoiceField(queryset=Claustro.objects.filter(activo=True), widget=forms.CheckboxSelectMultiple, required=False)

    class Meta:
        model = PlantillaNotificacion
        fields = (
            "nombre", "categoria", "asunto", "contenido",
            "roles_destinatarios", "claustros", "permite_envio_manual", "activa",
        )
        widgets = {"contenido": forms.Textarea(attrs={"rows": 5})}
        labels = {
            "categoria": "¿Para qué se usará?",
            "permite_envio_manual": "También permitir envíos manuales",
            "activa": "Plantilla disponible",
        }
        help_texts = {
            "categoria": "Para las fechas administrativas, elegí Mensajes de fechas y recordatorios.",
            "permite_envio_manual": "Permite elegir esta plantilla en la pantalla de envío manual de notificaciones.",
            "activa": "Una plantilla desactivada no se ofrece para nuevos envíos.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["roles_destinatarios"].initial = self.instance.roles_destinatarios
        if "categoria" in self.fields:
            self.fields["categoria"].choices = (
                ("calendario", "Mensajes de fechas y recordatorios"),
                ("jornada", "Avisos de la jornada electoral"),
                ("transaccional", "Respuestas a solicitudes"),
                ("manual", "Mensajes generales"),
            )
            if not self.instance.pk:
                self.initial["categoria"] = "calendario"
                self.initial["permite_envio_manual"] = False

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if not instancia.codigo:
            instancia.codigo = "plantilla-" + uuid4().hex
        instancia.roles_destinatarios = self.cleaned_data["roles_destinatarios"]
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia


class FormularioComunicacionFechaAdministrativa(forms.ModelForm):
    class Meta:
        model = ComunicacionFechaAdministrativa
        fields = ("codigo", "nombre", "referencia", "desplazamiento_dias", "hora_sugerida", "orden", "activa")
        widgets = {"hora_sugerida": forms.TimeInput(attrs={"type": "time"})}


class FormularioVarianteComunicacion(forms.ModelForm):
    class Meta:
        model = VarianteComunicacionFechaAdministrativa
        fields = ("plantilla", "criterio_adicional", "prioridad", "activa")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plantilla"].queryset = PlantillaNotificacion.objects.filter(
            activa=True,
            categoria=PlantillaNotificacion.Categoria.CALENDARIO,
        )


class FormularioEnviarNotificacion(forms.Form):
    plantilla = forms.ModelChoiceField(
        queryset=PlantillaNotificacion.objects.filter(activa=True, permite_envio_manual=True)
    )
    eleccion = forms.ModelChoiceField(queryset=Eleccion.objects.all(), required=False)
