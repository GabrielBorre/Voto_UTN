from django import forms
from django.db import transaction
from django.db.models import Q

from apps.elecciones.models import EleccionClaustro
from django.core.exceptions import ValidationError
from django.urls import reverse
from apps.partidos.services import (
    TIPOS_DOCUMENTO_CANDIDATO,
    buscar_elector_candidato,
    conflictos_de_cupo,
    sincronizar_puestos_en_preparacion,
)
from apps.parametros.models import Claustro
from apps.partidos.models import (
    Candidato,
    CargoElectivo,
    CupoPuestoClaustro,
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


class FormularioCargoElectivo(forms.ModelForm):
    ALCANCE_DEPARTAMENTAL = "departamental"
    ALCANCE_GENERAL = "general"

    tipo_alcance = forms.ChoiceField(
        label="Alcance del puesto",
        choices=(
            (ALCANCE_DEPARTAMENTAL, "Departamental: solo pueden postularse electores del departamento del puesto"),
            (ALCANCE_GENERAL, "General: puede postularse cualquier elector del claustro, sin importar su departamento"),
        ),
        widget=forms.RadioSelect(attrs={"class": "puesto-alcance-radio"}),
        initial=ALCANCE_GENERAL,
        help_text=(
            "Un puesto departamental se genera una vez por cada departamento habilitado del claustro; "
            "uno general, una sola vez por claustro."
        ),
    )

    class Meta:
        model = CargoElectivo
        fields = (
            "organo",
            "nombre",
            "descripcion",
            "tipo_alcance",
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
        if self.instance.pk and not self.is_bound:
            self.fields["tipo_alcance"].initial = (
                self.ALCANCE_DEPARTAMENTAL if self.instance.es_departamental else self.ALCANCE_GENERAL
            )
        cupos = {}
        if self.instance.pk:
            cupos = {cupo.claustro_id: cupo for cupo in self.instance.cupos_claustro.all()}
            asociados = set(self.instance.claustros_habilitados.values_list("pk", flat=True))
        else:
            asociados = set()
        self.claustros = list(
            Claustro.objects.filter(Q(activo=True) | Q(pk__in=asociados)).order_by("nombre")
        )
        for claustro in self.claustros:
            cupo = cupos.get(claustro.pk)
            self.fields[f"claustro_{claustro.pk}"] = forms.BooleanField(
                required=False, label=str(claustro), initial=claustro.pk in asociados,
            )
            self.fields[f"titulares_{claustro.pk}"] = forms.IntegerField(
                required=False, min_value=1, label="Titulares",
                initial=cupo.cantidad_titulares if cupo else 1,
            )
            self.fields[f"suplentes_{claustro.pk}"] = forms.IntegerField(
                required=False, min_value=1, label="Suplentes",
                initial=cupo.cantidad_suplentes if cupo else 1,
            )
            for nombre in ("titulares", "suplentes"):
                self.fields[f"{nombre}_{claustro.pk}"].widget.attrs["min"] = 1
            for prefijo in ("claustro", "titulares", "suplentes"):
                self.fields[f"{prefijo}_{claustro.pk}"].es_claustro = True

    @property
    def filas_claustros(self):
        return [
            {
                "claustro": claustro,
                "asociado": self[f"claustro_{claustro.pk}"],
                "titulares": self[f"titulares_{claustro.pk}"],
                "suplentes": self[f"suplentes_{claustro.pk}"],
            }
            for claustro in self.claustros
        ]

    def clean(self):
        datos = super().clean()
        departamental = datos.get("tipo_alcance") == self.ALCANCE_DEPARTAMENTAL
        self.instance.permite_filtrar_departamentos = departamental
        self.cupos = {}
        for claustro in self.claustros:
            if not datos.get(f"claustro_{claustro.pk}"):
                continue
            titulares = datos.get(f"titulares_{claustro.pk}")
            suplentes = datos.get(f"suplentes_{claustro.pk}")
            if f"titulares_{claustro.pk}" in self.errors or f"suplentes_{claustro.pk}" in self.errors:
                continue
            if not titulares or not suplentes:
                self.add_error(
                    f"titulares_{claustro.pk}",
                    f"Indicá al menos 1 titular y 1 suplente para {claustro}.",
                )
                continue
            self.cupos[claustro] = (titulares, suplentes)
            if self.instance.pk:
                conflictos = conflictos_de_cupo(self.instance, claustro, titulares, suplentes)
                if conflictos:
                    self.add_error(
                        f"titulares_{claustro.pk}",
                        f"Hay candidaturas cargadas fuera de esa cantidad en: {', '.join(conflictos)}.",
                    )
        return datos

    @transaction.atomic
    def save(self, commit=True):
        cargo = super().save(commit=commit)
        if not commit:
            return cargo
        cargo.claustros_habilitados.set(self.cupos.keys())
        cargo.cupos_claustro.exclude(claustro__in=self.cupos.keys()).delete()
        for claustro, (titulares, suplentes) in self.cupos.items():
            CupoPuestoClaustro.objects.update_or_create(
                puesto=cargo, claustro=claustro,
                defaults={"cantidad_titulares": titulares, "cantidad_suplentes": suplentes},
            )
        sincronizar_puestos_en_preparacion()
        return cargo

class FormularioParticipacionPartido(forms.ModelForm):
    eleccion_claustro = CampoClaustro(
        queryset=EleccionClaustro.objects.none(),
        label="Claustro",
    )
    puestos_eleccion = forms.ModelMultipleChoiceField(
        queryset=PuestoEleccion.objects.none(),
        label="Puestos de la lista",
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text="Elegí puestos del claustro de la lista. La carga de candidatos estará disponible al guardar.",
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
        puestos_disponibles = PuestoEleccion.objects.filter(
            eleccion_claustro__eleccion=eleccion,
            activo=True,
            puesto__activo=True,
            puesto__organo__activo=True,
        )
        claustro_id = (
            self.data.get(self.add_prefix("eleccion_claustro"), "")
            if self.is_bound
            else self.initial.get("eleccion_claustro", "")
        )
        claustro_id = str(getattr(claustro_id, "pk", claustro_id))
        claustro_catalogo_id = None
        if claustro_id.isdecimal():
            claustro_catalogo_id = EleccionClaustro.objects.filter(
                pk=claustro_id,
                eleccion=eleccion,
            ).values_list("claustro_id", flat=True).first()
            puestos_disponibles = puestos_disponibles.filter(
                eleccion_claustro_id=claustro_id,
            )
            if claustro_catalogo_id:
                puestos_disponibles = puestos_disponibles.filter(
                    puesto__claustros_habilitados=claustro_catalogo_id,
                )
        self.fields["puestos_eleccion"].queryset = puestos_disponibles.select_related(
            "puesto__organo",
            "eleccion_claustro__claustro",
            "eleccion_claustro_departamento__departamento",
        )
        self.fields["nombre_lista"].required = True
        self.fields["apoderado_nombre"].required = True
        estilizar_campos(self)
        self.fields["puestos_eleccion"].widget.attrs["class"] = "checkbox-list"

    def clean(self):
        datos = super().clean()
        claustro = datos.get("eleccion_claustro")
        puestos = datos.get("puestos_eleccion")
        if claustro and puestos and any(
            puesto.eleccion_claustro_id != claustro.id for puesto in puestos
        ):
            self.add_error(
                "puestos_eleccion",
                "Todos los puestos deben pertenecer al claustro seleccionado.",
            )
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
            puestos_disponibles = puestos_disponibles.filter(
                eleccion_claustro=participacion.eleccion_claustro,
                puesto__claustros_habilitados=participacion.eleccion_claustro.claustro_id,
            )
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
        self.fields["orden"].help_text = "Define la posición del candidato dentro de la lista."
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
