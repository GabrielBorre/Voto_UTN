from django import forms
from django.db import transaction
from django.db.models import Q

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import EleccionClaustroTurno
from apps.mesas.models import Mesa
from apps.parametros.models import Sede, Turno


class FormularioAsignacionAutoridad(forms.Form):
    candidatura = forms.ModelChoiceField(
        queryset=CandidaturaAutoridad.objects.none(),
        label="Persona candidata",
    )
    mesa = forms.ModelChoiceField(queryset=Mesa.objects.none(), label="Mesa")
    turno = forms.ModelChoiceField(queryset=Turno.objects.none(), label="Turno de trabajo")

    def __init__(self, *args, eleccion_claustro, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion_claustro = eleccion_claustro
        self.fields["candidatura"].queryset = CandidaturaAutoridad.objects.filter(
            registro_padron__eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
            registro_padron__asignacion_autoridad__isnull=True,
        ).select_related("registro_padron__elector")
        self.fields["mesa"].queryset = Mesa.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=eleccion_claustro,
        ).select_related(
            "eleccion_claustro_departamento__departamento",
            "eleccion_claustro_departamento__eleccion_claustro__claustro",
            "sede",
        )
        self.fields["mesa"].label_from_instance = lambda mesa: (
            f"Mesa {mesa.numero} · {mesa.eleccion_claustro_departamento.departamento.nombre} · {mesa.sede or 'Sin sede'}"
        )
        self.fields["turno"].queryset = Turno.objects.filter(
            elecciones_turno__eleccion_claustro=eleccion_claustro,
        ).order_by("hora_inicio", "nombre")
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-select"

    def clean(self):
        datos = super().clean()
        candidatura = datos.get("candidatura")
        mesa = datos.get("mesa")
        if candidatura and mesa:
            claustro_persona = candidatura.registro_padron.eleccion_claustro_departamento.eleccion_claustro_id
            claustro_mesa = mesa.eleccion_claustro_departamento.eleccion_claustro_id
            if claustro_persona != self.eleccion_claustro.id or claustro_mesa != self.eleccion_claustro.id:
                raise forms.ValidationError("La persona y la mesa deben pertenecer al claustro seleccionado.")
        return datos


class FormularioTurnosAutoridades(forms.Form):
    turnos = forms.ModelMultipleChoiceField(
        queryset=Turno.objects.none(),
        label="Turnos de trabajo",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, eleccion_claustro, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion_claustro = eleccion_claustro
        self.fields["turnos"].queryset = Turno.objects.filter(
            Q(activo=True) | Q(elecciones_turno__eleccion_claustro=eleccion_claustro)
        ).distinct().order_by("hora_inicio", "nombre")
        self.fields["turnos"].initial = eleccion_claustro.turnos_autoridad.values_list("turno_id", flat=True)
        self.fields["turnos"].widget.attrs["class"] = "checkbox-list"

    def clean_turnos(self):
        turnos = self.cleaned_data["turnos"]
        utilizados = set(
            AsignacionAutoridad.objects.filter(
                mesa__eleccion_claustro_departamento__eleccion_claustro=self.eleccion_claustro,
            ).values_list("turno_id", flat=True)
        )
        removidos = utilizados - set(turnos.values_list("id", flat=True))
        if removidos:
            raise forms.ValidationError("No se puede quitar un turno que ya tiene autoridades asignadas.")
        return turnos

    @transaction.atomic
    def guardar(self):
        turnos = self.cleaned_data["turnos"]
        seleccionados = set(turnos.values_list("id", flat=True))
        self.eleccion_claustro.turnos_autoridad.exclude(turno_id__in=seleccionados).delete()
        EleccionClaustroTurno.objects.bulk_create(
            [
                EleccionClaustroTurno(eleccion_claustro=self.eleccion_claustro, turno=turno)
                for turno in turnos
            ],
            ignore_conflicts=True,
        )


class FormularioArchivoAutoridades(forms.Form):
    archivo = forms.FileField(
        label="Archivo de candidatos",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "class": "input",
            }
        ),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = archivo.name.lower()
        if not nombre.endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Debe seleccionar un archivo CSV o Excel moderno (.xlsx). El formato .xls debe convertirse antes de cargarlo.")
        if archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar los 5 MB.")
        return archivo


class FormularioPreferenciaAutoridad(forms.ModelForm):
    class Meta:
        model = PreferenciaAutoridad
        fields = ("sede_preferida", "turno_preferido", "disponible")

    def __init__(self, *args, registro_padron, **kwargs):
        super().__init__(*args, **kwargs)
        self.registro_padron = registro_padron
        self.fields["sede_preferida"].queryset = Sede.objects.filter(pk=registro_padron.sede_id)
        self.fields["turno_preferido"].queryset = Turno.objects.filter(
            elecciones_turno__eleccion_claustro=registro_padron.eleccion_claustro_departamento.eleccion_claustro,
        ).distinct()
        for nombre, campo in self.fields.items():
            campo.widget.attrs["class"] = "form-check-input" if nombre == "disponible" else "form-select"
