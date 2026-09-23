from django import forms
from django.db import transaction
from django.db.models import Q

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import EleccionTurno
from apps.mesas.models import Mesa
from apps.parametros.models import Sede, Turno


class FormularioAsignacionAutoridad(forms.Form):
    candidatura = forms.ModelChoiceField(queryset=CandidaturaAutoridad.objects.none(), label="Candidato")
    mesa = forms.ModelChoiceField(queryset=Mesa.objects.none())
    turno = forms.ModelChoiceField(queryset=Turno.objects.none(), label="Turno de trabajo")

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["candidatura"].queryset = CandidaturaAutoridad.objects.filter(registro_padron__eleccion=eleccion).select_related("registro_padron__elector")
        self.fields["mesa"].queryset = Mesa.objects.filter(eleccion=eleccion).select_related("eleccion_claustro_departamento__eleccion_claustro__claustro")
        self.fields["turno"].queryset = Turno.objects.filter(elecciones_turno__eleccion=eleccion).order_by("hora_inicio", "nombre")
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select"


class FormularioTurnosAutoridades(forms.Form):
    turnos = forms.ModelMultipleChoiceField(
        queryset=Turno.objects.none(),
        label="Turnos de trabajo",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.fields["turnos"].queryset = Turno.objects.filter(
            Q(activo=True) | Q(elecciones_turno__eleccion=eleccion)
        ).distinct().order_by("hora_inicio", "nombre")
        self.fields["turnos"].initial = eleccion.elecciones_turno.values_list("turno_id", flat=True)
        self.fields["turnos"].widget.attrs["class"] = "checkbox-list"

    def clean_turnos(self):
        turnos = self.cleaned_data["turnos"]
        utilizados = set(
            AsignacionAutoridad.objects.filter(mesa__eleccion=self.eleccion).values_list("turno_id", flat=True)
        )
        removidos = utilizados - set(turnos.values_list("id", flat=True))
        if removidos:
            raise forms.ValidationError("No se puede quitar un turno que ya tiene autoridades asignadas.")
        return turnos

    @transaction.atomic
    def guardar(self):
        turnos = self.cleaned_data["turnos"]
        seleccionados = set(turnos.values_list("id", flat=True))
        self.eleccion.elecciones_turno.exclude(turno_id__in=seleccionados).delete()
        EleccionTurno.objects.bulk_create(
            [EleccionTurno(eleccion=self.eleccion, turno=turno) for turno in turnos],
            ignore_conflicts=True,
        )


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
