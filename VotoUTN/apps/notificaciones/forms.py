from django import forms

from apps.elecciones.models import Claustro, Eleccion, FechaAdministrativa, PlantillaNotificacion


class FormularioPlantillaNotificacion(forms.ModelForm):
    roles_destinatarios = forms.MultipleChoiceField(choices=FechaAdministrativa.RolDestinatario.choices, widget=forms.CheckboxSelectMultiple)
    claustros = forms.ModelMultipleChoiceField(queryset=Claustro.objects.filter(activo=True), widget=forms.CheckboxSelectMultiple, required=False)

    class Meta:
        model = PlantillaNotificacion
        fields = ("nombre", "asunto", "contenido", "roles_destinatarios", "claustros", "activa")
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


class FormularioEnviarNotificacion(forms.Form):
    plantilla = forms.ModelChoiceField(queryset=PlantillaNotificacion.objects.filter(activa=True))
    eleccion = forms.ModelChoiceField(queryset=Eleccion.objects.all(), required=False)
