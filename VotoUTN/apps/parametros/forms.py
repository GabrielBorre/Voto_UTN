from django import forms

from apps.elecciones.models import Claustro, Departamento, FechaAdministrativa, Sede, TipoJustificativo, Turno


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
    claustros = forms.ModelMultipleChoiceField(queryset=Claustro.objects.filter(activo=True), widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = FechaAdministrativa
        fields = ("nombre", "roles_destinatarios", "claustros", "asunto_notificacion", "mensaje_notificacion", "activa")
        widgets = {"mensaje_notificacion": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["roles_destinatarios"].initial = self.instance.roles_destinatarios
        for nombre in ("roles_destinatarios", "claustros"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre, campo in self.fields.items():
            if nombre not in ("roles_destinatarios", "claustros", "activa"):
                campo.widget.attrs.setdefault("class", "form-control")

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
