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
            eleccion_claustro = EleccionClaustro.objects.create(
                eleccion=eleccion,
                claustro=claustro,
                organizacion_departamentos=claustro.organizacion_departamentos,
            )
            EleccionClaustroSede.objects.bulk_create(
                [EleccionClaustroSede(eleccion_claustro=eleccion_claustro, sede=sede) for sede in sedes]
            )
            if (
                claustro.organizacion_departamentos
                == Claustro.OrganizacionDepartamentos.SIN_DEPARTAMENTO
            ):
                alcance = EleccionClaustroDepartamento.objects.create(
                    eleccion_claustro=eleccion_claustro,
                    departamento=None,
                )
                EleccionClaustroDepartamentoSede.objects.bulk_create(
                    [
                        EleccionClaustroDepartamentoSede(
                            eleccion_claustro_departamento=alcance,
                            sede=sede,
                        )
                        for sede in sedes
                    ]
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


class FormularioDepartamentosClaustro(forms.Form):
    departamentos = forms.ModelMultipleChoiceField(
        queryset=Departamento.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Departamentos habilitados",
    )

    def __init__(self, *args, eleccion_claustro, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion_claustro = eleccion_claustro
        actuales = eleccion_claustro.departamentos.filter(
            departamento__isnull=False,
        ).values_list("departamento_id", flat=True)
        self.fields["departamentos"].queryset = Departamento.objects.filter(
            Q(activo=True)
            | Q(elecciones_claustro_departamento__eleccion_claustro=eleccion_claustro)
        ).distinct()
        self.fields["departamentos"].initial = actuales
        self.fields["departamentos"].widget.attrs["class"] = "checkbox-list"

    def clean_departamentos(self):
        seleccionados = self.cleaned_data["departamentos"]
        ids_seleccionados = set(seleccionados.values_list("id", flat=True))
        configuraciones_removidas = self.eleccion_claustro.departamentos.filter(
            departamento__isnull=False,
        ).exclude(departamento_id__in=ids_seleccionados)
        departamentos_en_uso = []
        for configuracion in configuraciones_removidas.select_related("departamento"):
            if any(
                relacion.exists()
                for relacion in (
                    configuracion.mesas,
                    configuracion.registros_padron,
                    configuracion.puestos_electivos,
                    configuracion.listas_candidatos,
                )
            ):
                departamentos_en_uso.append(str(configuracion.departamento))
        if departamentos_en_uso:
            raise forms.ValidationError(
                "No se pueden quitar departamentos con padrón, mesas, puestos o listas asociados: "
                + ", ".join(departamentos_en_uso)
                + "."
            )
        return seleccionados

    @transaction.atomic
    def guardar(self):
        seleccionados = set(self.cleaned_data["departamentos"].values_list("id", flat=True))
        configuraciones = self.eleccion_claustro.departamentos.filter(departamento__isnull=False)
        actuales = set(configuraciones.values_list("departamento_id", flat=True))

        sedes = list(self.eleccion_claustro.sedes_habilitadas.values_list("sede_id", flat=True))
        for departamento_id in seleccionados - actuales:
            configuracion = EleccionClaustroDepartamento.objects.create(
                eleccion_claustro=self.eleccion_claustro,
                departamento_id=departamento_id,
            )
            EleccionClaustroDepartamentoSede.objects.bulk_create(
                [
                    EleccionClaustroDepartamentoSede(
                        eleccion_claustro_departamento=configuracion,
                        sede_id=sede_id,
                    )
                    for sede_id in sedes
                ]
            )

        removidas = configuraciones.filter(departamento_id__in=actuales - seleccionados)
        EleccionClaustroDepartamentoSede.objects.filter(
            eleccion_claustro_departamento__in=removidas,
        ).delete()
        removidas.delete()


class FormularioPrepararClaustro(forms.ModelForm):
    class Meta:
        model = EleccionClaustro
        fields = ("fecha_votacion", "maximo_votantes_por_mesa")
        labels = {
            "fecha_votacion": "Fecha de votación",
            "maximo_votantes_por_mesa": "Máximo de electores por mesa",
        }
        widgets = {
            "fecha_votacion": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "maximo_votantes_por_mesa": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.required = True
