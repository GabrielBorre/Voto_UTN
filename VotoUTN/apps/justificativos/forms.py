from django import forms

from apps.elecciones.models import JustificativoAusencia, RegistroPadron, TipoJustificativo


class FormularioJustificativo(forms.ModelForm):
    registro_padron = forms.ModelChoiceField(queryset=RegistroPadron.objects.none(), label="Eleccion")

    class Meta:
        model = JustificativoAusencia
        fields = ("registro_padron", "tipo", "detalle", "documento")
        widgets = {"detalle": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, elector=None, **kwargs):
        super().__init__(*args, **kwargs)
        consulta_padron = RegistroPadron.objects.filter(activo=True).select_related("eleccion")
        if elector is not None:
            consulta_padron = consulta_padron.filter(elector=elector)
        self.fields["registro_padron"].queryset = consulta_padron
        self.fields["tipo"].queryset = TipoJustificativo.objects.filter(activo=True)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-control")

    def clean_documento(self):
        documento = self.cleaned_data.get("documento")
        if documento is None:
            return documento
        extensiones = (".pdf", ".jpg", ".jpeg", ".png")
        if not documento.name.lower().endswith(extensiones) or documento.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Adjunte un PDF o imagen de hasta 5 MB.")
        return documento


class FormularioResolucionJustificativo(forms.Form):
    estado = forms.ChoiceField(choices=((JustificativoAusencia.Estado.APROBADO, "Aprobar"), (JustificativoAusencia.Estado.RECHAZADO, "Rechazar")))
    observacion_resolucion = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
