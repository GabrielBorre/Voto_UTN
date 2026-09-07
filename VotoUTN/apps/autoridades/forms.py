from django import forms

from apps.elecciones.models import CandidaturaAutoridad, Mesa, PreferenciaAutoridad, Sede, Turno


class FormularioAsignacionAutoridad(forms.Form):
    candidatura = forms.ModelChoiceField(queryset=CandidaturaAutoridad.objects.none(), label="Candidato")
    mesa = forms.ModelChoiceField(queryset=Mesa.objects.none())

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["candidatura"].queryset = CandidaturaAutoridad.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector")
        self.fields["mesa"].queryset = Mesa.objects.filter(eleccion=eleccion).select_related("eleccion_claustro_departamento__eleccion_claustro__claustro")
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select"


class FormularioArchivoAutoridades(forms.Form):
    archivo = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}))

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if not archivo.name.lower().endswith(".csv") or archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Debe seleccionar un CSV de hasta 5 MB.")
        return archivo


class FormularioPreferenciaAutoridad(forms.ModelForm):
    class Meta:
        model = PreferenciaAutoridad
        fields = ("sede_preferida", "turno_preferido", "disponible")

    def __init__(self, *args, eleccion, registro_padron, **kwargs):
        super().__init__(*args, **kwargs)
        self.registro_padron = registro_padron
        self.fields["sede_preferida"].queryset = Sede.objects.filter(pk=registro_padron.sede_id)
        self.fields["turno_preferido"].queryset = Turno.objects.filter(elecciones_turno__eleccion=eleccion).distinct()
        for nombre, campo in self.fields.items():
            campo.widget.attrs["class"] = "form-check-input" if nombre == "disponible" else "form-select"
