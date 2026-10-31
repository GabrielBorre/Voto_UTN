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
        fields = ("nombre", "abreviatura", "organizacion_departamentos", "activo")
        labels = {
            "organizacion_departamentos": "Organización del claustro",
        }
        help_texts = {
            "abreviatura": "Identificación breve que se mostrará en listados y reportes.",
            "organizacion_departamentos": (
                "Define el valor inicial para las nuevas elecciones. No modifica elecciones existentes."
            ),
        }


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
            "codigo", "nombre", "descripcion", "estado_eleccion", "envia_mensaje", "plantilla_mensaje", "permite_recordatorios", "plantilla_recordatorio",
            "roles_destinatarios", "alcance_todos_claustros", "claustros",
            "criterio_destinatarios", "activa",
        )
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}
        labels = {
            "estado_eleccion": "Estado de la elección",
            "envia_mensaje": "Habilitar mensaje principal",
            "permite_recordatorios": "Habilitar recordatorios",
            "plantilla_mensaje": "Plantilla sugerida del mensaje",
            "plantilla_recordatorio": "Plantilla sugerida de los recordatorios",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ("plantilla_mensaje", "plantilla_recordatorio"):
            self.fields[nombre].queryset = self.fields[nombre].queryset.filter(activa=True).exclude(categoria="transaccional")
        if self.instance.pk:
            self.fields["roles_destinatarios"].initial = self.instance.roles_destinatarios
        for nombre in ("roles_destinatarios", "claustros"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre, campo in self.fields.items():
            if nombre not in ("roles_destinatarios", "claustros", "activa", "alcance_todos_claustros"):
                campo.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        datos = super().clean()
        for flag, campo in (("envia_mensaje", "plantilla_mensaje"), ("permite_recordatorios", "plantilla_recordatorio")):
            plantilla = datos.get(campo)
            if datos.get(flag) and not plantilla:
                self.add_error(campo, "Seleccione una plantilla para este envío.")
            if plantilla and (not plantilla.activa or not set(plantilla.roles_destinatarios).issubset(datos.get("roles_destinatarios", []))):
                self.add_error(campo, "Seleccione una plantilla activa compatible con los destinatarios.")
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
