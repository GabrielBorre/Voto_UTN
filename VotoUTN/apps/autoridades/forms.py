from django import forms
from django.db import transaction
from django.db.models import Q

from apps.autoridades.models import AsignacionAutoridad, CandidaturaAutoridad, PreferenciaAutoridad
from apps.elecciones.models import EleccionClaustroTurno
from apps.mesas.models import Mesa
from apps.parametros.models import Departamento, Sede, Turno


class FormularioFiltroAsignaciones(forms.Form):
    departamento = forms.ModelChoiceField(
        queryset=Departamento.objects.none(), required=False, empty_label="Todos los departamentos",
    )
    sede = forms.ModelChoiceField(queryset=Sede.objects.none(), required=False, empty_label="Todas las sedes")
    cobertura = forms.ChoiceField(required=False, choices=(
        ("", "Todas las mesas"), ("titulares", "Con titulares faltantes"),
        ("suplentes", "Con suplentes faltantes"), ("completa", "Con cobertura completa"),
    ))

    def __init__(self, *args, claustro, **kwargs):
        super().__init__(*args, **kwargs)
        mesas = Mesa.objects.filter(eleccion_claustro_departamento__eleccion_claustro=claustro)
        self.fields["departamento"].queryset = Departamento.objects.filter(
            pk__in=mesas.values("eleccion_claustro_departamento__departamento_id"),
        ).order_by("nombre")
        self.fields["sede"].queryset = Sede.objects.filter(pk__in=mesas.values("sede_id")).order_by("nombre")
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "input"


class FormularioConfiguracionAutoridades(forms.ModelForm):
    class Meta:
        from apps.autoridades.models import ConfiguracionAutoridades
        model = ConfiguracionAutoridades
        fields = ("modo", "reacomodar_titulares", "permitir_mesa_distinta", "permitir_cambio_sede")
        labels = {
            "modo": "Modo de asignación",
            "reacomodar_titulares": "Permitir cambio de mesa",
            "permitir_mesa_distinta": "Votar en mesa distinta",
            "permitir_cambio_sede": "Permitir cambio de sede",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["modo"].widget.attrs["class"] = "input"
        self.fields["modo"].choices = (
            ("nomina", "Nómina común"),
            ("aleatorio", "Sorteo aleatorio"),
        )
        if self.instance.modo == "manual":
            self.initial["modo"] = "aleatorio"
        for nombre in ("permitir_cambio_sede", "reacomodar_titulares", "permitir_mesa_distinta"):
            self.fields[nombre].widget.attrs["class"] = "form-check-input"

    def clean(self):
        datos = super().clean()
        if datos.get("modo") == "nomina" and datos.get("permitir_cambio_sede") and not datos.get("reacomodar_titulares"):
            self.add_error("permitir_cambio_sede", "Para cambiar de sede también debe habilitarse «Permitir cambio de mesa».")
        if datos.get("modo") == "nomina" and datos.get("permitir_cambio_sede") and datos.get("permitir_mesa_distinta"):
            self.add_error("permitir_mesa_distinta", "«Votar en mesa distinta» mantiene la misma sede; no se combina con cambio de sede.")
        if datos.get("modo") == "nomina" and datos.get("reacomodar_titulares") and datos.get("permitir_mesa_distinta"):
            self.add_error("permitir_mesa_distinta", "Elegí entre reacomodar el padrón o asignar la autoridad en una mesa de votación distinta.")
        if datos.get("modo") != "nomina":
            # Las opciones son exclusivas de la nómina, pero se conservan ocultas
            # para que cambiar temporalmente de modo no borre las preferencias.
            datos["permitir_cambio_sede"] = self.instance.permitir_cambio_sede
            datos["reacomodar_titulares"] = self.instance.reacomodar_titulares
            datos["permitir_mesa_distinta"] = self.instance.permitir_mesa_distinta
        return datos


class FormularioSeleccionMesa(forms.Form):
    turno = forms.ModelChoiceField(queryset=Turno.objects.none(), label="Turno")
    tipo = forms.ChoiceField(choices=AsignacionAutoridad.Tipo.choices, label="Función")
    busqueda = forms.CharField(required=False, max_length=180, label="Buscar por nombre, apellido, documento o legajo",
                               widget=forms.TextInput(attrs={"type": "search", "autocomplete": "off", "placeholder": "Escribí para filtrar las personas disponibles"}))
    registro = forms.ModelChoiceField(queryset=None, label="Persona disponible de la mesa")
    orden = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput)
    asignacion_a_reemplazar = forms.ModelChoiceField(
        queryset=AsignacionAutoridad.objects.none(), required=False,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, mesa, **kwargs):
        from apps.padron.models import RegistroPadron
        from apps.autoridades.seleccion_manual import personas_disponibles
        super().__init__(*args, **kwargs)
        self.fields["turno"].queryset = Turno.objects.filter(
            elecciones_turno__eleccion_claustro=mesa.eleccion_claustro_departamento.eleccion_claustro,
        ).order_by("hora_inicio", "nombre")
        turnos = list(self.fields["turno"].queryset)
        self.fields["asignacion_a_reemplazar"].queryset = AsignacionAutoridad.objects.filter(
            mesa=mesa, estado=AsignacionAutoridad.Estado.ASIGNADA,
        ).select_related("registro_padron__elector", "turno")
        origen = self.data if self.is_bound else self.initial
        try:
            reemplazo_id = int(origen.get("asignacion_a_reemplazar") or 0)
        except (ValueError, TypeError):
            reemplazo_id = 0
        self.reemplazo = self.fields["asignacion_a_reemplazar"].queryset.filter(pk=reemplazo_id).first()
        if self.reemplazo:
            self.initial.update(turno=self.reemplazo.turno_id, tipo=self.reemplazo.tipo, orden=self.reemplazo.orden_suplencia)
            self.fields["turno"].disabled = True
            self.fields["tipo"].disabled = True
        elif not self.is_bound:
            validos = {str(t.pk): t.pk for t in turnos}
            self.initial["turno"] = validos.get(str(self.initial.get("turno")), turnos[0].pk if turnos else None)
            self.initial.setdefault("tipo", "titular")
        turno_elegido = self.initial.get("turno") if self.reemplazo or not self.is_bound else self.data.get("turno")
        try:
            turno_id = int(turno_elegido or 0)
        except (ValueError, TypeError):
            turno_id = 0
        disponibles = [(r, compatibles) for r, compatibles in personas_disponibles(mesa, turnos) if compatibles]
        etiqueta = lambda r: f"{r.elector.nombre_completo} · {r.elector.dni} · {r.elector.legajo or ''}"
        self.datos_personas = [{"id": r.pk, "nombre": etiqueta(r), "turnos": compatibles} for r, compatibles in disponibles]
        self.fields["registro"].queryset = RegistroPadron.objects.filter(
            pk__in=[r.pk for r, compatibles in disponibles if turno_id in compatibles],
        ).select_related("elector").order_by("elector__apellido", "elector__nombre", "pk")
        self.fields["registro"].label_from_instance = etiqueta
        self.fields["registro"].empty_label = "Seleccioná una persona"
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "input"
        self.fields["registro"].widget.attrs.update(size=7)


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
            f"Mesa {mesa.codigo} · {mesa.eleccion_claustro_departamento.departamento.nombre} · {mesa.sede or 'Sin sede'}"
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


class FormularioBusquedaCandidato(forms.Form):
    busqueda = forms.CharField(label="Documento, legajo o nombre", max_length=180)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["busqueda"].widget.attrs.update({"class": "input", "placeholder": "DNI, CUIL, legajo o nombre"})


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
        utilizados = set(AsignacionAutoridad.objects.filter(
            mesa__eleccion_claustro_departamento__eleccion_claustro=self.eleccion_claustro,
        ).values_list("turno_id", flat=True))
        if utilizados - set(turnos.values_list("id", flat=True)):
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


class FormularioArchivoNomina(forms.Form):
    archivo = forms.FileField(
        label="Archivo de nómina",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "class": "input",
            }
        ),
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo is None:
            return None
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
