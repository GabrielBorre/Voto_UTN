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
            "codigo", "nombre", "categoria", "descripcion", "asunto", "contenido",
            "roles_destinatarios", "claustros", "permite_envio_manual", "activa",
        )
        widgets = {"contenido": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["roles_destinatarios"].initial = self.instance.roles_destinatarios

    def save(self, commit=True):
        instancia = super().save(commit=False)
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
