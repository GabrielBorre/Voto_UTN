from django import forms
from django.db import transaction

from .models import (
    Claustro,
    Departamento,
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    EleccionTurno,
    Mesa,
    Sede,
    Turno,
)


class FormularioEleccion(forms.ModelForm):
    sedes = forms.ModelMultipleChoiceField(queryset=Sede.objects.none())
    claustros = forms.ModelMultipleChoiceField(queryset=Claustro.objects.none())
    departamentos = forms.ModelMultipleChoiceField(queryset=Departamento.objects.none())
    turnos = forms.ModelMultipleChoiceField(queryset=Turno.objects.none())

    class Meta:
        model = Eleccion
        fields = ("nombre", "fecha_inicio", "fecha_fin", "estado", "habilitada")
        widgets = {
            "fecha_inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "fecha_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sedes"].queryset = Sede.objects.filter(activa=True)
        self.fields["claustros"].queryset = Claustro.objects.filter(activo=True)
        self.fields["departamentos"].queryset = Departamento.objects.filter(activo=True)
        self.fields["turnos"].queryset = Turno.objects.filter(activo=True)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["sedes"].widget.attrs["class"] = "form-select"
        self.fields["claustros"].widget.attrs["class"] = "form-select"
        self.fields["departamentos"].widget.attrs["class"] = "form-select"
        self.fields["turnos"].widget.attrs["class"] = "form-select"

    @transaction.atomic
    def save(self, commit=True):
        eleccion = super().save(commit=commit)
        if not commit:
            return eleccion

        sedes = self.cleaned_data["sedes"]
        EleccionSede.objects.bulk_create(
            [EleccionSede(eleccion=eleccion, sede=sede) for sede in sedes]
        )
        EleccionTurno.objects.bulk_create(
            [EleccionTurno(eleccion=eleccion, turno=turno) for turno in self.cleaned_data["turnos"]]
        )
        for claustro in self.cleaned_data["claustros"]:
            eleccion_claustro = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro)
            EleccionClaustroSede.objects.bulk_create(
                [EleccionClaustroSede(eleccion_claustro=eleccion_claustro, sede=sede) for sede in sedes]
            )
            for departamento in self.cleaned_data["departamentos"]:
                configuracion = EleccionClaustroDepartamento.objects.create(
                    eleccion_claustro=eleccion_claustro,
                    departamento=departamento,
                )
                EleccionClaustroDepartamentoSede.objects.bulk_create(
                    [
                        EleccionClaustroDepartamentoSede(
                            eleccion_claustro_departamento=configuracion,
                            sede=sede,
                        )
                        for sede in sedes
                    ]
                )
        return eleccion


class FormularioGenerarMesas(forms.Form):
    configuracion = forms.ModelChoiceField(queryset=EleccionClaustroDepartamento.objects.none(), label="Claustro y departamento")
    sede = forms.ModelChoiceField(queryset=Sede.objects.none())
    turno = forms.ModelChoiceField(queryset=Turno.objects.none())
    cantidad = forms.IntegerField(min_value=1, max_value=500, initial=1)

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.fields["configuracion"].queryset = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion
        ).select_related("eleccion_claustro__claustro", "departamento")
        self.fields["sede"].queryset = Sede.objects.filter(elecciones_sede__eleccion=eleccion).distinct()
        self.fields["turno"].queryset = Turno.objects.filter(elecciones_turno__eleccion=eleccion).distinct()
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-select" if isinstance(field, forms.ModelChoiceField) else "form-control"

    def clean(self):
        cleaned_data = super().clean()
        configuracion = cleaned_data.get("configuracion")
        sede = cleaned_data.get("sede")
        if configuracion and sede and not configuracion.sedes_habilitadas.filter(
            sede=sede,
        ).exists():
            self.add_error("sede", "La sede no esta habilitada para el departamento seleccionado.")
        return cleaned_data

    @transaction.atomic
    def generar(self):
        ultimo_numero = Mesa.objects.filter(eleccion=self.eleccion).order_by("-numero").values_list("numero", flat=True).first() or 0
        configuracion = self.cleaned_data["configuracion"]
        sede = self.cleaned_data["sede"]
        turno = self.cleaned_data["turno"]
        mesas = [
            Mesa(
                eleccion=self.eleccion,
                numero=ultimo_numero + indice,
                eleccion_claustro_departamento=configuracion,
                sede=sede,
                turno=turno,
            )
            for indice in range(1, self.cleaned_data["cantidad"] + 1)
        ]
        for mesa in mesas:
            mesa.full_clean()
        Mesa.objects.bulk_create(mesas)
        return mesas
