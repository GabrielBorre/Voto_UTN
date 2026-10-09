from django import forms

from apps.elecciones.models import EleccionClaustroDepartamento, EleccionClaustroDepartamentoSede
from apps.padron.models import (
    BaseCondicionPadron,
    ConfiguracionSedesClaustro,
    ConfiguracionSedePadronVotacion,
    CondicionInclusionPadronVotacion,
    PadronVotacion,
    ReglaAsignacionSede,
    ReglaSedeClaustro,
)
from apps.partidos.models import PuestoEleccion
from apps.padron.services import alcances_con_sedes_multiples
from apps.parametros.models import Sede


class FormularioArchivoPadron(forms.Form):
    archivo = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}))

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        nombre = archivo.name.lower()
        if not nombre.endswith((".csv", ".xlsx", ".xls")):
            raise forms.ValidationError("Debe seleccionar un archivo CSV o Excel (.xlsx/.xls).")
        if archivo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar los 5 MB.")
        return archivo


class FormularioPadronVotacion(forms.ModelForm):
    class Meta:
        model = PadronVotacion
        fields = ("nombre", "puestos")
        widgets = {"puestos": forms.CheckboxSelectMultiple}

    def __init__(self, *args, eleccion_claustro, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion_claustro = eleccion_claustro
        self.fields["puestos"].queryset = PuestoEleccion.objects.filter(
            eleccion_claustro=eleccion_claustro, activo=True,
        ).select_related("puesto__organo", "eleccion_claustro_departamento__departamento")
        self.fields["puestos"].label_from_instance = lambda puesto: str(puesto)
        self.fields["nombre"].widget.attrs["class"] = "form-control"

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.eleccion_claustro = self.eleccion_claustro
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia


class FormularioCondicionInclusion(forms.ModelForm):
    class Meta:
        model = CondicionInclusionPadronVotacion
        fields = ("campo", "operador", "valor")


class FormularioConfiguracionSede(forms.ModelForm):
    class Meta:
        model = ConfiguracionSedePadronVotacion
        fields = ("eleccion_claustro_departamento", "sede_predeterminada")

    def __init__(self, *args, padron_votacion, **kwargs):
        super().__init__(*args, **kwargs)
        self.padron_votacion = padron_votacion
        self.fields["eleccion_claustro_departamento"].queryset = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro=padron_votacion.eleccion_claustro,
        ).select_related("departamento")
        self.fields["sede_predeterminada"].queryset = EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=padron_votacion.eleccion_claustro,
            sede__activa=True,
        ).select_related("sede", "eleccion_claustro_departamento__departamento")
        self.fields["sede_predeterminada"].label_from_instance = lambda item: f"{item.eleccion_claustro_departamento.nombre_alcance}: {item.sede.nombre}"

    def clean(self):
        datos = super().clean()
        sede = datos.get("sede_predeterminada")
        departamento = datos.get("eleccion_claustro_departamento")
        if sede and departamento and sede.eleccion_claustro_departamento_id != departamento.id:
            self.add_error("sede_predeterminada", "Elegí una sede habilitada para el departamento seleccionado.")
        return datos


class FormularioReglaSede(forms.ModelForm):
    class Meta:
        model = ReglaAsignacionSede
        fields = ("orden", "campo", "operador", "valor", "sede_destino")

    def __init__(self, *args, configuracion, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuracion = configuracion
        self.instance.configuracion = configuracion
        self.fields["sede_destino"].queryset = EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento=configuracion.eleccion_claustro_departamento,
            sede__activa=True,
        ).select_related("sede")
        self.fields["sede_destino"].label_from_instance = lambda item: item.sede.nombre

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.configuracion = self.configuracion
        if commit:
            instancia.save()
        return instancia


class FormularioReglaSedeClaustro(forms.ModelForm):
    class Meta:
        model = ReglaSedeClaustro
        fields = (
            "orden",
            "campo",
            "operador",
            "valor",
            "sede_destino",
            "aplicar_a_todos",
            "alcances_especificos",
        )
        widgets = {
            "orden": forms.HiddenInput(),
            "campo": forms.Select(attrs={"class": "form-select"}),
            "operador": forms.Select(attrs={"class": "form-select"}),
            "valor": forms.TextInput(attrs={"class": "form-control"}),
            "sede_destino": forms.Select(attrs={"class": "form-select"}),
            "aplicar_a_todos": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "alcances_especificos": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, eleccion_claustro, configuracion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion_claustro = eleccion_claustro
        self.configuracion = configuracion or getattr(self.instance, "configuracion", None)
        if self.configuracion:
            self.instance.configuracion = self.configuracion
            if "orden" not in self.initial:
                ultimo_orden = self.configuracion.reglas.order_by("-orden").values_list("orden", flat=True).first() or 0
                self.initial["orden"] = ultimo_orden + 1
        alcances = alcances_con_sedes_multiples(eleccion_claustro)
        self.fields["alcances_especificos"].queryset = alcances
        self.fields["alcances_especificos"].label_from_instance = lambda item: item.nombre_alcance
        self.fields["sede_destino"].queryset = Sede.objects.filter(
            activa=True,
            elecciones_departamento_sede__eleccion_claustro_departamento__in=alcances,
        ).distinct().order_by("nombre")
        self.fields["alcances_especificos"].required = False
        self.fields["aplicar_a_todos"].initial = True
        self.fields["orden"].disabled = True
        self.fields["aplicar_a_todos"].label = "Todos los departamentos disponibles"
        self.fields["alcances_especificos"].label = "Departamentos incluidos en esta regla"
        self.fields["alcances_especificos"].help_text = "Desmarcá la opción anterior para elegir departamentos específicos."
        self.fields["orden"].label = "Prioridad"
        self.fields["sede_destino"].label = "Sede que se asignará"

    def clean(self):
        datos = super().clean()
        destino = datos.get("sede_destino")
        aplicar_a_todos = datos.get("aplicar_a_todos")
        alcances_seleccionados = datos.get("alcances_especificos")
        if not aplicar_a_todos and not alcances_seleccionados:
            self.add_error("alcances_especificos", "Seleccioná uno o más departamentos para esta regla.")
        if destino:
            alcances_destino = alcances_con_sedes_multiples(self.eleccion_claustro).filter(
                sedes_habilitadas__sede=destino,
                sedes_habilitadas__sede__activa=True,
            ).distinct()
            if not aplicar_a_todos and alcances_seleccionados:
                if not alcances_destino.filter(pk__in=alcances_seleccionados).exists():
                    self.add_error("sede_destino", "La sede debe estar habilitada en al menos uno de los departamentos seleccionados.")
            elif not alcances_destino.exists():
                self.add_error("sede_destino", "La sede no está habilitada en ningún departamento con varias sedes.")
        return datos

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.configuracion = self.configuracion
        if commit:
            instancia.save()
            self.save_m2m()
        return instancia
