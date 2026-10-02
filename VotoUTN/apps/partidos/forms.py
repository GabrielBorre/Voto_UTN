from django import forms
from django.db import transaction
from django.db.models import Q

from apps.elecciones.models import EleccionClaustro, EleccionClaustroDepartamento
from django.core.exceptions import ValidationError
from django.urls import reverse
from apps.partidos.services import TIPOS_DOCUMENTO_CANDIDATO, buscar_elector_candidato
from apps.parametros.models import Departamento
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    ListaCandidatos,
    OrganoElectivo,
    ParticipacionPartido,
    Partido,
    PuestoEleccion,
)


class CampoClaustro(forms.ModelChoiceField):
    def label_from_instance(self, objeto):
        return str(objeto.claustro)


class CampoDepartamento(forms.ModelChoiceField):
    def label_from_instance(self, objeto):
        return str(objeto)


class CampoMultipleClaustro(forms.ModelMultipleChoiceField):
    def label_from_instance(self, objeto):
        return str(objeto.claustro)


class CampoMultipleDepartamento(forms.ModelMultipleChoiceField):
    def label_from_instance(self, objeto):
        return str(objeto)


def estilizar_campos(formulario):
    for campo in formulario.fields.values():
        campo.widget.attrs.setdefault("class", "input")


class FormularioPartido(forms.ModelForm):
    class Meta:
        model = Partido
        fields = ("nombre", "sigla")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilizar_campos(self)


class FormularioOrganoElectivo(forms.ModelForm):
    class Meta:
        model = OrganoElectivo
        fields = ("nombre", "descripcion", "activo")
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}


class FormularioCargoElectivo(forms.ModelForm):
    class Meta:
        model = CargoElectivo
        fields = (
            "organo",
            "nombre",
            "permite_filtrar_claustros",
            "permite_filtrar_departamentos",
            "descripcion",
            "activo",
        )
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        organos = OrganoElectivo.objects.filter(activo=True)
        if self.instance.pk:
            organos = OrganoElectivo.objects.filter(
                Q(activo=True) | Q(pk=self.instance.organo_id)
            )
        self.fields["organo"].queryset = organos.order_by("nombre")

class FormularioParticipacionPartido(forms.ModelForm):
    eleccion_claustro = CampoClaustro(
        queryset=EleccionClaustro.objects.none(),
        label="Claustro",
    )

    class Meta:
        model = ParticipacionPartido
        fields = (
            "eleccion_claustro",
            "numero_lista",
            "nombre_lista",
            "apoderado_nombre",
            "apoderado_email",
        )

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.instance.eleccion = eleccion
        self.fields["eleccion_claustro"].queryset = EleccionClaustro.objects.filter(
            eleccion=eleccion,
        ).select_related("claustro").order_by("claustro__nombre")
        self.fields["nombre_lista"].required = True
        self.fields["apoderado_nombre"].required = True
        estilizar_campos(self)

class FormularioPuestoEleccion(forms.ModelForm):
    TIPO_CLAUSTRO = "claustro"
    TIPO_DEPARTAMENTO = "departamento"
    TIPOS_ALCANCE = (
        (TIPO_CLAUSTRO, "Sin filtro por departamento"),
        (TIPO_DEPARTAMENTO, "Limitado a un departamento"),
    )

    tipo_alcance = forms.ChoiceField(
        label="Tipo de alcance",
        choices=TIPOS_ALCANCE,
        help_text="El claustro siempre es concreto; elegí si además se restringe a un departamento.",
    )
    eleccion_claustro = CampoClaustro(
        queryset=EleccionClaustro.objects.none(),
        label="Claustro seleccionado",
    )

    class Meta:
        model = PuestoEleccion
        fields = (
            "puesto",
            "tipo_alcance",
            "eleccion_claustro",
            "eleccion_claustro_departamento",
            "cantidad_titulares",
            "cantidad_suplentes",
            "activo",
        )

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.fields["puesto"].queryset = CargoElectivo.objects.filter(
            activo=True,
            organo__activo=True,
        ).select_related("organo")
        self.fields["eleccion_claustro"].queryset = EleccionClaustro.objects.filter(
            eleccion=eleccion,
        ).select_related("claustro").order_by("claustro__nombre")
        self.fields["eleccion_claustro_departamento"].queryset = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion,
            departamento__isnull=False,
        ).select_related("eleccion_claustro__claustro", "departamento")
        self.fields["eleccion_claustro_departamento"].required = False
        self.fields["puesto"].label = "Puesto a habilitar"
        self.fields["eleccion_claustro"].label = "Claustro seleccionado"
        self.fields["eleccion_claustro"].help_text = "Elegí el claustro particular al que corresponde este alcance."
        self.fields["eleccion_claustro_departamento"].label = "Departamento (opcional)"
        self.fields["eleccion_claustro_departamento"].help_text = (
            "Es obligatorio cuando el alcance está limitado a un departamento."
        )
        if self.instance.pk and not self.is_bound:
            self.fields["tipo_alcance"].initial = (
                self.TIPO_DEPARTAMENTO
                if self.instance.eleccion_claustro_departamento_id
                else self.TIPO_CLAUSTRO
            )
        estilizar_campos(self)

    def clean(self):
        datos = super().clean()
        claustro = datos.get("eleccion_claustro")
        departamento = datos.get("eleccion_claustro_departamento")
        puesto = datos.get("puesto")
        tipo_alcance = datos.get("tipo_alcance")
        if tipo_alcance == self.TIPO_CLAUSTRO:
            datos["eleccion_claustro_departamento"] = None
            departamento = None
        elif tipo_alcance == self.TIPO_DEPARTAMENTO:
            if not departamento:
                self.add_error("eleccion_claustro_departamento", "Seleccione un departamento.")
            if puesto and not puesto.permite_filtrar_departamentos:
                self.add_error("tipo_alcance", "Este puesto no admite alcance por departamento.")
        if claustro and departamento and departamento.eleccion_claustro_id != claustro.id:
            self.add_error("eleccion_claustro_departamento", "El departamento debe pertenecer al claustro seleccionado.")
        return datos


class FormularioImportacionCandidaturas(forms.Form):
    archivo = forms.FileField(
        label="Archivo CSV",
        help_text="Utilice la plantilla provista. Se admiten archivos UTF-8 separados por punto y coma o coma.",
    )

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        if archivo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 2 MB.")
        if not archivo.name.lower().endswith(".csv"):
            raise forms.ValidationError("Debe seleccionar un archivo CSV.")
        return archivo


class FormularioHabilitacionPuesto(forms.Form):
    puesto = forms.ModelChoiceField(
        queryset=CargoElectivo.objects.none(),
        label="Puesto a habilitar",
    )
    limitar_por_claustros = forms.BooleanField(
        label="Limitar a claustros determinados",
        required=False,
        help_text="Si no se activa, se incluyen todos los claustros configurados en la elección.",
    )
    claustros = CampoMultipleClaustro(
        queryset=EleccionClaustro.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text="Seleccione los claustros solamente cuando active el filtro anterior.",
    )
    limitar_por_departamentos = forms.BooleanField(
        label="Limitar a departamentos determinados",
        required=False,
        help_text="Si no se activa, no se aplica ningún filtro por departamento.",
    )
    departamentos = CampoMultipleDepartamento(
        queryset=Departamento.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text="Seleccione los departamentos solamente cuando active el filtro anterior.",
    )
    cantidad_titulares = forms.IntegerField(label="Cantidad de titulares", min_value=1)
    cantidad_suplentes = forms.IntegerField(label="Cantidad de suplentes", min_value=0, initial=0)
    activo = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.fields["puesto"].queryset = CargoElectivo.objects.filter(
            activo=True,
            organo__activo=True,
        ).select_related("organo")
        self.fields["claustros"].queryset = EleccionClaustro.objects.filter(
            eleccion=eleccion,
        ).select_related("claustro")
        self.fields["departamentos"].queryset = Departamento.objects.filter(
            elecciones_claustro_departamento__eleccion_claustro__eleccion=eleccion,
        ).distinct().order_by("nombre")
        estilizar_campos(self)
        for nombre in ("claustros", "departamentos"):
            self.fields[nombre].widget.attrs["class"] = "checkbox-list"
        for nombre in ("limitar_por_claustros", "limitar_por_departamentos", "activo"):
            self.fields[nombre].widget.attrs.pop("class", None)

    def clean(self):
        datos = super().clean()
        puesto = datos.get("puesto")
        limitar_claustros = datos.get("limitar_por_claustros")
        limitar_departamentos = datos.get("limitar_por_departamentos")
        claustros = datos.get("claustros")
        departamentos = datos.get("departamentos")

        if limitar_claustros and puesto and not puesto.permite_filtrar_claustros:
            self.add_error(
                "limitar_por_claustros",
                "El parámetro del puesto no permite limitar por claustros.",
            )
        if limitar_claustros and not claustros:
            self.add_error("claustros", "Seleccione al menos un claustro.")

        if limitar_departamentos:
            if puesto and not puesto.permite_filtrar_departamentos:
                self.add_error(
                    "limitar_por_departamentos",
                    "El parámetro del puesto no permite limitar por departamentos.",
                )
            if not departamentos:
                self.add_error("departamentos", "Seleccione al menos un departamento.")

        claustros_efectivos = claustros if limitar_claustros and claustros else self.fields["claustros"].queryset
        if puesto and claustros_efectivos and not limitar_departamentos:
            repetidos = PuestoEleccion.objects.filter(
                puesto=puesto,
                eleccion_claustro__in=claustros_efectivos,
                eleccion_claustro_departamento__isnull=True,
            ).values_list("eleccion_claustro__claustro__nombre", flat=True)
            if repetidos:
                self.add_error("claustros", f"El puesto ya está habilitado para: {', '.join(repetidos)}.")
        if puesto and limitar_departamentos and departamentos and claustros_efectivos:
            alcances_departamentales = EleccionClaustroDepartamento.objects.filter(
                eleccion_claustro__in=claustros_efectivos,
                departamento__in=departamentos,
            )
            if not alcances_departamentales.exists():
                self.add_error(
                    "departamentos",
                    "No existen combinaciones entre los claustros y departamentos seleccionados.",
                )
            repetidos = PuestoEleccion.objects.filter(
                puesto=puesto,
                eleccion_claustro_departamento__in=alcances_departamentales,
            ).values_list("eleccion_claustro_departamento__departamento__nombre", flat=True)
            if repetidos:
                self.add_error("departamentos", f"El puesto ya está habilitado para: {', '.join(repetidos)}.")
        datos["claustros_efectivos"] = claustros_efectivos
        return datos

    @transaction.atomic
    def guardar(self):
        configuraciones = []
        datos = self.cleaned_data
        comunes = {
            "puesto": datos["puesto"],
            "cantidad_titulares": datos["cantidad_titulares"],
            "cantidad_suplentes": datos["cantidad_suplentes"],
            "activo": datos["activo"],
        }
        if not datos["limitar_por_departamentos"]:
            for eleccion_claustro in datos["claustros_efectivos"]:
                configuracion = PuestoEleccion(eleccion_claustro=eleccion_claustro, **comunes)
                configuracion.full_clean()
                configuracion.save()
                configuraciones.append(configuracion)
        else:
            alcances_departamentales = EleccionClaustroDepartamento.objects.filter(
                eleccion_claustro__in=datos["claustros_efectivos"],
                departamento__in=datos["departamentos"],
            ).select_related("eleccion_claustro")
            for alcance_departamental in alcances_departamentales:
                configuracion = PuestoEleccion(
                    eleccion_claustro=alcance_departamental.eleccion_claustro,
                    eleccion_claustro_departamento=alcance_departamental,
                    **comunes,
                )
                configuracion.full_clean()
                configuracion.save()
                configuraciones.append(configuracion)
        return configuraciones


class FormularioListaCandidatos(forms.ModelForm):
    class Meta:
        model = ListaCandidatos
        fields = ("puesto_eleccion",)

    def __init__(self, *args, participacion, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.participacion = participacion
        eleccion = participacion.eleccion
        usados = ListaCandidatos.objects.filter(participacion=participacion).exclude(pk=self.instance.pk).values_list(
            "puesto_eleccion_id",
            flat=True,
        )
        puestos_disponibles = PuestoEleccion.objects.filter(
            eleccion_claustro__eleccion=eleccion,
            activo=True,
        )
        if participacion.eleccion_claustro_id:
            puestos_disponibles = puestos_disponibles.filter(eleccion_claustro=participacion.eleccion_claustro)
        self.fields["puesto_eleccion"].queryset = puestos_disponibles.exclude(pk__in=usados).select_related(
            "puesto__organo",
            "eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
        )
        self.fields["puesto_eleccion"].label = "Puesto al que se presenta la lista"
        estilizar_campos(self)

    def clean(self):
        datos = super().clean()
        puesto = datos.get("puesto_eleccion")
        if puesto:
            if self.instance.participacion.eleccion_claustro_id and self.instance.participacion.eleccion_claustro_id != puesto.eleccion_claustro_id:
                self.add_error("puesto_eleccion", "El puesto corresponde a otro claustro.")
            self.instance.eleccion_claustro = puesto.eleccion_claustro
            self.instance.eleccion_claustro_departamento = puesto.eleccion_claustro_departamento
            self.instance.nombre = str(puesto.puesto)
        return datos


class FormularioCandidato(forms.ModelForm):
    tipo_documento = forms.ChoiceField(label="Tipo de documento", choices=TIPOS_DOCUMENTO_CANDIDATO, initial="DNI")
    documento = forms.CharField(label="Documento", max_length=20, help_text="DNI o CUIL según el padrón; para legajo se busca en su campo propio.")
    nombre_padron = forms.CharField(label="Nombre completo en el padrón", required=False, disabled=True)

    class Meta:
        model = Candidato
        fields = ("tipo_documento", "documento", "nombre_padron", "tipo", "orden")

    def __init__(self, *args, lista, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.lista = lista
        self.url_busqueda = reverse("buscar-elector-candidato", args=(lista.participacion.eleccion_id, lista.pk))
        if self.instance.elector_id:
            elector = self.instance.elector
            tipo = elector.tipo_documento.upper()
            self.initial.update(tipo_documento=tipo if tipo in {"DNI", "CUIL"} else "LEGAJO",
                                documento=elector.dni if tipo in {"DNI", "CUIL"} else elector.legajo,
                                nombre_padron=elector.nombre_completo)
        self.fields["nombre_padron"].widget.attrs["readonly"] = True
        if not lista.puesto_eleccion_id:
            self.fields["cargo"] = forms.CharField(initial=self.instance.cargo, max_length=120)
        estilizar_campos(self)

    def clean(self):
        datos = super().clean()
        self.instance.elector = None
        self.initial["nombre_padron"] = ""
        if datos.get("documento") and datos.get("tipo_documento"):
            try:
                self.instance.elector = buscar_elector_candidato(
                    eleccion=self.instance.lista.participacion.eleccion,
                    tipo_documento=datos["tipo_documento"], documento=datos["documento"],
                    puesto=self.instance.lista.puesto_eleccion or self.instance.lista,
                )
                self.initial["nombre_padron"] = self.instance.elector.nombre_completo
            except ValidationError as error:
                self.add_error("documento", error)
        if self.instance.lista.puesto_eleccion_id:
            limite = (
                self.instance.lista.puesto_eleccion.cantidad_titulares
                if datos.get("tipo") == Candidato.Tipo.TITULAR
                else self.instance.lista.puesto_eleccion.cantidad_suplentes
            )
            if datos.get("orden") and datos["orden"] > limite:
                self.add_error("orden", f"El orden máximo configurado para este tipo es {limite}.")
        elif datos.get("cargo"):
            self.instance.cargo = datos["cargo"]
        return datos

    def _get_validation_exclusions(self):
        exclusiones = super()._get_validation_exclusions()
        # El DNI canónico se obtiene del elector; debe seguir validando unicidad.
        if self.instance.elector_id:
            exclusiones.discard("dni")
        if self.instance.lista_id:
            exclusiones.discard("lista")
        return exclusiones

    def _update_errors(self, errores):
        if hasattr(errores, "error_dict") and "dni" in errores.error_dict:
            errores.error_dict.setdefault("documento", []).extend(errores.error_dict.pop("dni"))
        if hasattr(errores, "error_dict") and "lista" in errores.error_dict:
            errores.error_dict.setdefault("__all__", []).extend(errores.error_dict.pop("lista"))
        super()._update_errors(errores)
