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
    sedes = forms.ModelMultipleChoiceField(queryset=Sede.objects.none(), widget=forms.CheckboxSelectMultiple)
    claustros = forms.ModelMultipleChoiceField(queryset=Claustro.objects.none(), widget=forms.CheckboxSelectMultiple)
    departamentos = forms.ModelMultipleChoiceField(queryset=Departamento.objects.none(), widget=forms.CheckboxSelectMultiple)
    turnos = forms.ModelMultipleChoiceField(queryset=Turno.objects.none(), widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Eleccion
        fields = ("nombre", "fecha_inicio", "fecha_fin")
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
        for nombre in ("sedes", "claustros", "departamentos", "turnos"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre in ("nombre", "fecha_inicio", "fecha_fin"):
            self.fields[nombre].widget.attrs.setdefault("class", "form-control")

    @transaction.atomic
    def save(self, commit=True):
        eleccion = super().save(commit=commit)
        if not commit:
            return eleccion

        eleccion.estado = Eleccion.Estado.BORRADOR
        eleccion.habilitada = False
        eleccion.save(update_fields=("estado", "habilitada"))

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


class FormularioEditarEleccion(forms.ModelForm):
    class Meta:
        model = Eleccion
        fields = ("nombre", "fecha_inicio", "fecha_fin")
        widgets = {
            "fecha_inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "fecha_fin": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"


class FormularioAlcanceSedes(forms.Form):
    sedes = forms.ModelMultipleChoiceField(queryset=Sede.objects.none(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, eleccion, objeto, tipo, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.objeto = objeto
        self.tipo = tipo
        if tipo == "claustro":
            disponibles = Sede.objects.filter(elecciones_sede__eleccion=eleccion).distinct()
            actuales = objeto.sedes_habilitadas.values_list("sede_id", flat=True)
        else:
            disponibles = Sede.objects.filter(elecciones_claustro_sede__eleccion_claustro=objeto.eleccion_claustro).distinct()
            actuales = objeto.sedes_habilitadas.values_list("sede_id", flat=True)
        self.fields["sedes"].queryset = disponibles
        self.fields["sedes"].initial = actuales
        self.fields["sedes"].widget.attrs["class"] = "checkbox-list"

    def clean_sedes(self):
        sedes = self.cleaned_data["sedes"]
        if not sedes:
            raise forms.ValidationError("Debe quedar al menos una sede habilitada.")
        actuales = set(self.fields["sedes"].initial)
        removidas = actuales - set(sedes.values_list("id", flat=True))
        if self.tipo == "claustro":
            mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=self.objeto, sede_id__in=removidas)
        else:
            mesas = Mesa.objects.filter(eleccion_claustro_departamento=self.objeto, sede_id__in=removidas)
        if mesas.exists():
            raise forms.ValidationError("No se puede quitar una sede utilizada por mesas existentes.")
        return sedes

    @transaction.atomic
    def guardar(self):
        seleccionadas = set(self.cleaned_data["sedes"].values_list("id", flat=True))
        actuales = set(self.fields["sedes"].initial)
        nuevas = seleccionadas - actuales
        removidas = actuales - seleccionadas
        if self.tipo == "claustro":
            for sede_id in nuevas:
                EleccionClaustroSede.objects.get_or_create(eleccion_claustro=self.objeto, sede_id=sede_id)
                for configuracion in self.objeto.departamentos.all():
                    EleccionClaustroDepartamentoSede.objects.get_or_create(eleccion_claustro_departamento=configuracion, sede_id=sede_id)
            EleccionClaustroDepartamentoSede.objects.filter(eleccion_claustro_departamento__eleccion_claustro=self.objeto, sede_id__in=removidas).delete()
            EleccionClaustroSede.objects.filter(eleccion_claustro=self.objeto, sede_id__in=removidas).delete()
        else:
            for sede_id in nuevas:
                EleccionClaustroDepartamentoSede.objects.get_or_create(eleccion_claustro_departamento=self.objeto, sede_id=sede_id)
            EleccionClaustroDepartamentoSede.objects.filter(eleccion_claustro_departamento=self.objeto, sede_id__in=removidas).delete()


class FormularioSede(forms.ModelForm):
    class Meta:
        model = Sede
        fields = ("nombre", "codigo", "activa")


class FormularioClaustro(forms.ModelForm):
    class Meta:
        model = Claustro
        fields = ("nombre", "codigo", "activo")


class FormularioDepartamento(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = ("nombre", "codigo", "activo")


class FormularioTurno(forms.ModelForm):
    class Meta:
        model = Turno
        fields = ("nombre", "hora_inicio", "hora_fin", "activo")
        widgets = {
            "hora_inicio": forms.TimeInput(attrs={"type": "time"}),
            "hora_fin": forms.TimeInput(attrs={"type": "time"}),
        }


def preparar_formulario_parametro(formulario):
    for campo in formulario.fields.values():
        if isinstance(campo.widget, forms.CheckboxInput):
            campo.widget.attrs["class"] = "form-check-input"
        else:
            campo.widget.attrs.setdefault("class", "form-control")
    return formulario


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
