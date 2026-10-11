from django import forms

from apps.autoridades.models import AsignacionAutoridad
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo

class FormularioJustificativo(forms.ModelForm):
    class Meta:
        model = JustificativoAusencia
        fields = ("ausencia", "tipo", "detalle", "documento")
        widgets = {"detalle": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, registro_padron=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.registro_padron = registro_padron
        self.fields["tipo"].queryset = TipoJustificativo.objects.filter(activo=True)
        self.fields["ausencia"].label = "Ausencia a justificar"
        self.fields["ausencia"].choices = [
            (valor, etiqueta) for valor, etiqueta in JustificativoAusencia.Ausencia.choices
            if valor in self.ausencias_disponibles()
        ]
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-control")

    def ausencias_disponibles(self):
        if self.registro_padron is None:
            return set()
        permitidas = {JustificativoAusencia.Ausencia.VOTAR}
        if AsignacionAutoridad.objects.filter(registro_padron=self.registro_padron).exists():
            permitidas.add(JustificativoAusencia.Ausencia.AUTORIDAD)
        usadas = set(
            JustificativoAusencia.objects.filter(registro_padron=self.registro_padron).values_list("ausencia", flat=True)
        )
        return permitidas - usadas

    def clean(self):
        datos = super().clean()
        if self.registro_padron is None:
            raise forms.ValidationError("No existe un padrón activo para presentar el justificativo.")
        if not self.ausencias_disponibles():
            raise forms.ValidationError("Ya presentó el máximo de justificativos permitidos.")
        return datos

    def save(self, commit=True):
        justificativo = super().save(commit=False)
        justificativo.registro_padron = self.registro_padron
        if commit:
            justificativo.save()
            self.save_m2m()
        return justificativo

    def clean_documento(self):
        documento = self.cleaned_data.get("documento")
        if documento is None:
            return documento
        extensiones = (".pdf", ".jpg", ".jpeg", ".png")
        if not documento.name.lower().endswith(extensiones) or documento.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Adjunte un PDF o imagen de hasta 5 MB.")
        return documento


class FormularioResolucionJustificativo(forms.Form):
    estado = forms.ChoiceField(
        label="Resolución",
        choices=(
            (JustificativoAusencia.Estado.APROBADO, "Aprobar"),
            (JustificativoAusencia.Estado.RECHAZADO, "Rechazar"),
        ),
    )
    observacion_resolucion = forms.CharField(
        label="Observación de la resolución",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
