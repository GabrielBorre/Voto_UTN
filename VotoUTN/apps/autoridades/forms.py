from django import forms
from django.forms.models import ModelChoiceIteratorValue

from apps.autoridades.models import CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import EleccionClaustro
from apps.mesas.models import Mesa
from apps.parametros.models import Sede, Turno


class SelectorConClaustro(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if isinstance(value, ModelChoiceIteratorValue) and value.instance is not None:
            objeto = value.instance
            if isinstance(objeto, EleccionClaustro):
                option["attrs"]["data-claustro"] = objeto.pk
            elif isinstance(objeto, Mesa):
                option["attrs"]["data-claustro"] = objeto.eleccion_claustro_departamento.eleccion_claustro_id
            elif isinstance(objeto, CandidaturaAutoridad):
                option["attrs"]["data-claustro"] = objeto.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id
        return option


class FormularioAsignacionAutoridad(forms.Form):
    claustro = forms.ModelChoiceField(queryset=EleccionClaustro.objects.none(), label="1. Seleccioná el claustro", widget=SelectorConClaustro)
    mesa = forms.ModelChoiceField(queryset=Mesa.objects.none(), label="2. Seleccioná una mesa", widget=SelectorConClaustro)
    candidatura = forms.ModelChoiceField(queryset=CandidaturaAutoridad.objects.none(), label="3. Seleccioná una persona", widget=SelectorConClaustro)

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["claustro"].queryset = EleccionClaustro.objects.filter(eleccion=eleccion).select_related("claustro")
        self.fields["claustro"].label_from_instance = lambda configuracion: configuracion.claustro.nombre
        self.fields["candidatura"].queryset = CandidaturaAutoridad.objects.filter(
            registro_padron__eleccion=eleccion,
            registro_padron__asignacion_autoridad__isnull=True,
        ).select_related("registro_padron__elector", "registro_padron__eleccion_claustro_departamento__eleccion_claustro")
        self.fields["mesa"].queryset = Mesa.objects.filter(eleccion=eleccion, eleccion_claustro_departamento__isnull=False).select_related("eleccion_claustro_departamento__departamento", "eleccion_claustro_departamento__eleccion_claustro__claustro", "sede")
        self.fields["mesa"].label_from_instance = lambda mesa: (
            f"Mesa {mesa.numero} · {mesa.eleccion_claustro_departamento.eleccion_claustro.claustro.nombre} · "
            f"{mesa.eleccion_claustro_departamento.departamento.nombre} · {mesa.sede or 'Sin sede'}"
        )
        self.fields["mesa"].widget.attrs.update({"data-filtrado-por-claustro": "true", "disabled": "disabled"})
        self.fields["mesa"].empty_label = "Elegí primero un claustro"
        self.fields["candidatura"].widget.attrs.update({"data-filtrado-por-claustro": "true", "disabled": "disabled"})
        self.fields["candidatura"].empty_label = "Elegí primero un claustro y una mesa"
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select"

    def clean(self):
        datos = super().clean()
        configuracion_claustro = datos.get("claustro")
        candidatura = datos.get("candidatura")
        mesa = datos.get("mesa")
        if configuracion_claustro and mesa and mesa.eleccion_claustro_departamento.eleccion_claustro_id != configuracion_claustro.pk:
            self.add_error("mesa", "La mesa debe pertenecer al claustro seleccionado.")
        if configuracion_claustro and candidatura and candidatura.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id != configuracion_claustro.pk:
            self.add_error("candidatura", "La persona debe pertenecer al claustro seleccionado.")
        if candidatura and mesa:
            claustro_candidato = candidatura.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id
            claustro_mesa = mesa.eleccion_claustro_departamento.eleccion_claustro_id
            if claustro_candidato != claustro_mesa:
                self.add_error("candidatura", "La persona debe pertenecer al mismo claustro que la mesa.")
        return datos


class FormularioArchivoAutoridades(forms.Form):
    archivo = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}))

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = archivo.name.lower()
        if not nombre.endswith((".csv", ".xlsx", ".xls")):
            raise forms.ValidationError("Debe seleccionar un archivo CSV o Excel (.csv/.xlsx/.xls).")
        if archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar los 5 MB.")
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
