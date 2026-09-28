from django import forms
from django.db import transaction
from django.db.models import Q

from apps.elecciones.models import EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import Elector
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
        return f"{objeto.eleccion_claustro.claustro} / {objeto.departamento}"


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
    class Meta:
        model = ParticipacionPartido
        fields = (
            "codigo_presentacion",
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
        ).select_related("claustro")
        self.fields["codigo_presentacion"].required = True
        self.fields["nombre_lista"].required = True
        self.fields["apoderado_nombre"].required = True
        estilizar_campos(self)

    def clean_codigo_presentacion(self):
        codigo = self.cleaned_data["codigo_presentacion"].strip()
        if ParticipacionPartido.objects.filter(
            eleccion=self.eleccion,
            codigo_presentacion__iexact=codigo,
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("El código de presentación ya está utilizado en esta elección.")
        return codigo


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
        ).select_related("claustro")
        self.fields["eleccion_claustro_departamento"].queryset = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion,
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
        self.fields["puesto_eleccion"].queryset = PuestoEleccion.objects.filter(
            eleccion_claustro__eleccion=eleccion,
            activo=True,
        ).exclude(pk__in=usados).select_related(
            "puesto__organo",
            "eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
        )
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
    dni_elector = forms.CharField(
        label="DNI de elector vinculado",
        required=False,
        help_text="Opcional. Dejelo vacio para cargar una persona que no integra el padron.",
    )

    class Meta:
        model = Candidato
        fields = ("dni_elector", "identificador_persona", "nombre", "dni", "correo_electronico", "tipo", "orden")

    def __init__(self, *args, lista, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.lista = lista
        self.fields["nombre"].required = False
        self.fields["dni"].required = False
        if self.instance.elector_id:
            self.fields["dni_elector"].initial = self.instance.elector.dni
        if not lista.puesto_eleccion_id:
            self.fields["cargo"] = forms.CharField(initial=self.instance.cargo, max_length=120)
        estilizar_campos(self)

    def clean(self):
        datos = super().clean()
        dni_elector = datos.get("dni_elector", "").strip()
        if not dni_elector:
            self.instance.elector = None
        else:
            elector = Elector.objects.filter(dni=dni_elector).first()
            if elector is None:
                self.add_error("dni_elector", "No existe un elector con ese DNI.")
            else:
                self.instance.elector = elector
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
