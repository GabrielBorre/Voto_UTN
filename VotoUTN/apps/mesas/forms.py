from django import forms
from django.db import transaction

from apps.elecciones.models import (
    EleccionClaustroDepartamento,
    Mesa,
    Sede,
    Turno,
)


class FormularioGenerarMesas(forms.Form):
    configuracion = forms.ModelChoiceField(
        queryset=EleccionClaustroDepartamento.objects.none(),
        label="Claustro y departamento",
    )
    sede = forms.ModelChoiceField(queryset=Sede.objects.none())
    turno = forms.ModelChoiceField(queryset=Turno.objects.none())
    cantidad = forms.IntegerField(min_value=1, max_value=500, initial=1)

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.fields["configuracion"].queryset = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion,
        ).select_related("eleccion_claustro__claustro", "departamento")
        self.fields["sede"].queryset = Sede.objects.filter(
            elecciones_sede__eleccion=eleccion,
        ).distinct()
        self.fields["turno"].queryset = Turno.objects.filter(
            elecciones_turno__eleccion=eleccion,
        ).distinct()
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select" if isinstance(field, forms.ModelChoiceField) else "form-control"
            )

    def clean(self):
        cleaned_data = super().clean()
        configuracion = cleaned_data.get("configuracion")
        sede = cleaned_data.get("sede")
        if configuracion and sede and not configuracion.sedes_habilitadas.filter(
            sede=sede,
        ).exists():
            self.add_error(
                "sede",
                "La sede no esta habilitada para el departamento seleccionado.",
            )
        return cleaned_data

    @transaction.atomic
    def generar(self):
        ultimo_numero = (
            Mesa.objects.filter(eleccion=self.eleccion)
            .order_by("-numero")
            .values_list("numero", flat=True)
            .first()
            or 0
        )
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
