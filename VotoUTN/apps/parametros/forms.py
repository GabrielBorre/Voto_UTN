from django import forms

from apps.justificativos.models import TipoJustificativo
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede, Turno


class FormularioTipoJustificativo(forms.ModelForm):
    class Meta:
        model = TipoJustificativo
        fields = ("nombre", "activo")


class FormularioSede(forms.ModelForm):
    class Meta:
        model = Sede
        fields = ("nombre", "activa")


class FormularioClaustro(forms.ModelForm):
    class Meta:
        model = Claustro
        fields = ("nombre", "activo")


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


class FormularioFechaAdministrativa(forms.ModelForm):
    roles_destinatarios = forms.MultipleChoiceField(
        choices=FechaAdministrativa.RolDestinatario.choices,
        widget=forms.CheckboxSelectMultiple,
    )
    claustros = forms.ModelMultipleChoiceField(
        queryset=Claustro.objects.filter(activo=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = FechaAdministrativa
        fields = (
            "codigo", "nombre", "descripcion", "modalidad_sugerida", "duracion_sugerida_dias",
            "roles_destinatarios", "alcance_todos_claustros", "claustros",
            "criterio_destinatarios", "evento_disparador_sugerido", "activa",
        )
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["roles_destinatarios"].initial = self.instance.roles_destinatarios
        for nombre in ("roles_destinatarios", "claustros"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre, campo in self.fields.items():
            if nombre not in ("roles_destinatarios", "claustros", "activa", "alcance_todos_claustros"):
                campo.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        datos = super().clean()
        if not datos.get("alcance_todos_claustros") and not datos.get("claustros"):
            self.add_error("claustros", "Seleccione al menos un claustro o marque todos los claustros.")
        return datos

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.roles_destinatarios = self.cleaned_data["roles_destinatarios"]
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia


def preparar_formulario_parametro(formulario):
    for campo in formulario.fields.values():
        if isinstance(campo.widget, forms.CheckboxInput):
            campo.widget.attrs["class"] = "form-check-input"
        elif isinstance(campo.widget, forms.CheckboxSelectMultiple):
            campo.widget.attrs.setdefault("class", "checkbox-list")
        else:
            campo.widget.attrs.setdefault("class", "form-control")
    return formulario
