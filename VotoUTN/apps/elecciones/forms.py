from django import forms
from django.db import transaction
from django.db.models import Q

from .models import (
    Eleccion,
    EleccionClaustro,
    EleccionClaustroDepartamento,
    EleccionClaustroDepartamentoSede,
    EleccionClaustroSede,
    EleccionSede,
    FechaAdministrativaEleccion,
)
from apps.mesas.models import Mesa
from apps.padron.models import RegistroPadron
from apps.parametros.models import Claustro, Departamento, FechaAdministrativa, Sede


class FormularioEleccion(forms.ModelForm):
    sedes = forms.ModelMultipleChoiceField(queryset=Sede.objects.none(), widget=forms.CheckboxSelectMultiple)
    claustros = forms.ModelMultipleChoiceField(queryset=Claustro.objects.none(), widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Eleccion
        fields = (
            "nombre",
            "fecha_inicio",
            "fecha_fin",
        )
        labels = {
            "nombre": "Nombre de la elección",
            "fecha_inicio": "Inicio del proceso electoral",
            "fecha_fin": "Fin del proceso electoral",
        }
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sedes"].queryset = Sede.objects.filter(activa=True)
        self.fields["claustros"].queryset = Claustro.objects.filter(activo=True)
        for nombre in ("sedes", "claustros"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre in self.Meta.fields:
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
        for claustro in self.cleaned_data["claustros"]:
            eleccion_claustro = EleccionClaustro.objects.create(eleccion=eleccion, claustro=claustro)
            EleccionClaustroSede.objects.bulk_create(
                [EleccionClaustroSede(eleccion_claustro=eleccion_claustro, sede=sede) for sede in sedes]
            )
        return eleccion


class FormularioFechasAdministrativasEleccion(forms.Form):
    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.definiciones_fechas = list(
            FechaAdministrativa.objects.filter(
                Q(activa=True) | Q(programaciones__eleccion=eleccion),
            ).distinct().prefetch_related("claustros")
        )
        programaciones = {
            programacion.fecha_administrativa_id: programacion
            for programacion in eleccion.fechas_administrativas.all()
        }
        for definicion in self.definiciones_fechas:
            programacion = programaciones.get(definicion.id)
            self.fields[f"fecha_{definicion.id}_seleccionada"] = forms.BooleanField(
                required=False,
                label=definicion.nombre,
                initial=programacion is not None,
            )
            self.fields[f"fecha_{definicion.id}_valor"] = forms.DateField(
                required=False,
                label="Fecha",
                initial=programacion.fecha if programacion else None,
                widget=forms.DateInput(attrs={"type": "date"}),
            )

    def clean(self):
        cleaned_data = super().clean()
        for definicion in self.definiciones_fechas:
            seleccionada = cleaned_data.get(f"fecha_{definicion.id}_seleccionada")
            fecha = cleaned_data.get(f"fecha_{definicion.id}_valor")
            if seleccionada and not fecha:
                self.add_error(f"fecha_{definicion.id}_valor", "Debe indicar una fecha.")
            if seleccionada and fecha and not self.eleccion.fecha_inicio <= fecha <= self.eleccion.fecha_fin:
                self.add_error(
                    f"fecha_{definicion.id}_valor",
                    "Debe estar dentro del periodo completo de la eleccion.",
                )
        return cleaned_data

    @transaction.atomic
    def guardar(self):
        for definicion in self.definiciones_fechas:
            seleccionada = self.cleaned_data.get(f"fecha_{definicion.id}_seleccionada")
            if seleccionada:
                FechaAdministrativaEleccion.objects.update_or_create(
                    eleccion=self.eleccion,
                    fecha_administrativa=definicion,
                    defaults={"fecha": self.cleaned_data[f"fecha_{definicion.id}_valor"]},
                )
            else:
                FechaAdministrativaEleccion.objects.filter(
                    eleccion=self.eleccion,
                    fecha_administrativa=definicion,
                ).delete()


class FormularioEditarEleccion(forms.ModelForm):
    class Meta:
        model = Eleccion
        fields = FormularioEleccion.Meta.fields
        labels = FormularioEleccion.Meta.labels
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}),
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


class FormularioPrepararClaustro(forms.ModelForm):
    departamentos = forms.ModelMultipleChoiceField(queryset=Departamento.objects.none(), widget=forms.CheckboxSelectMultiple)
    sedes = forms.ModelMultipleChoiceField(queryset=Sede.objects.none(), widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = EleccionClaustro
        fields = ("fecha_votacion", "maximo_votantes_por_mesa")
        widgets = {"fecha_votacion": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["departamentos"].queryset = Departamento.objects.filter(activo=True)
        self.fields["sedes"].queryset = Sede.objects.filter(elecciones_sede__eleccion=self.instance.eleccion).distinct()
        self.fields["departamentos"].initial = self.instance.departamentos.values_list("departamento_id", flat=True)
        self.fields["sedes"].initial = self.instance.sedes_habilitadas.values_list("sede_id", flat=True)
        for nombre in ("departamentos", "sedes"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre in ("fecha_votacion", "maximo_votantes_por_mesa"):
            self.fields[nombre].widget.attrs["class"] = "form-control"

    def clean_sedes(self):
        sedes = self.cleaned_data["sedes"]
        if not sedes:
            raise forms.ValidationError("Debe seleccionar al menos una sede habilitada.")
        actuales = set(self.instance.sedes_habilitadas.values_list("sede_id", flat=True))
        removidas = actuales - set(sedes.values_list("id", flat=True))
        if RegistroPadron.objects.filter(
            eleccion_claustro_departamento__eleccion_claustro=self.instance,
            eleccion_claustro_departamento__sedes_habilitadas__sede_id__in=removidas,
        ).exists():
            raise forms.ValidationError("No se puede quitar una sede utilizada por un padrón importado.")
        return sedes

    @transaction.atomic
    def save(self, commit=True):
        instancia = super().save(commit=commit)
        if not commit:
            return instancia
        sedes = self.cleaned_data["sedes"]
        seleccionadas = set(sedes.values_list("id", flat=True))
        instancia.sedes_habilitadas.exclude(sede_id__in=seleccionadas).delete()
        for sede in sedes:
            EleccionClaustroSede.objects.get_or_create(eleccion_claustro=instancia, sede=sede)
        for departamento in self.cleaned_data["departamentos"]:
            configuracion, _ = EleccionClaustroDepartamento.objects.get_or_create(eleccion_claustro=instancia, departamento=departamento)
            for sede in sedes:
                EleccionClaustroDepartamentoSede.objects.get_or_create(eleccion_claustro_departamento=configuracion, sede=sede)
        return instancia
