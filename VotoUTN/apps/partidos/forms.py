from django import forms

from apps.elecciones.models import EleccionClaustro, EleccionClaustroDepartamento
from apps.padron.models import Elector
from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido, Partido


class CampoClaustro(forms.ModelChoiceField):
    def label_from_instance(self, objeto):
        return str(objeto.claustro)


class CampoDepartamento(forms.ModelChoiceField):
    def label_from_instance(self, objeto):
        return f"{objeto.eleccion_claustro.claustro} / {objeto.departamento}"


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


class FormularioParticipacionPartido(forms.ModelForm):
    class Meta:
        model = ParticipacionPartido
        fields = ("partido", "numero_lista", "nombre_lista")

    def __init__(self, *args, eleccion, **kwargs):
        super().__init__(*args, **kwargs)
        self.eleccion = eleccion
        self.instance.eleccion = eleccion
        ocupados = ParticipacionPartido.objects.filter(eleccion=eleccion).exclude(pk=self.instance.pk).values_list("partido_id", flat=True)
        self.fields["partido"].queryset = Partido.objects.filter(activo=True).exclude(pk__in=ocupados)
        estilizar_campos(self)

    def clean_numero_lista(self):
        numero = self.cleaned_data["numero_lista"].strip()
        if ParticipacionPartido.objects.filter(eleccion=self.eleccion, numero_lista=numero).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("El numero de lista ya esta utilizado en esta eleccion.")
        return numero


class FormularioListaCandidatos(forms.ModelForm):
    eleccion_claustro = CampoClaustro(queryset=EleccionClaustro.objects.none(), label="Claustro")
    eleccion_claustro_departamento = CampoDepartamento(
        queryset=EleccionClaustroDepartamento.objects.none(),
        label="Departamento",
        required=False,
    )

    class Meta:
        model = ListaCandidatos
        fields = ("nombre", "eleccion_claustro", "eleccion_claustro_departamento")

    def __init__(self, *args, participacion, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.participacion = participacion
        eleccion = participacion.eleccion
        self.fields["eleccion_claustro"].queryset = EleccionClaustro.objects.filter(eleccion=eleccion).select_related("claustro")
        self.fields["eleccion_claustro_departamento"].queryset = EleccionClaustroDepartamento.objects.filter(
            eleccion_claustro__eleccion=eleccion,
        ).select_related("eleccion_claustro__claustro", "departamento")
        estilizar_campos(self)

    def clean(self):
        datos = super().clean()
        claustro = datos.get("eleccion_claustro")
        departamento = datos.get("eleccion_claustro_departamento")
        if claustro and departamento and departamento.eleccion_claustro_id != claustro.id:
            self.add_error("eleccion_claustro_departamento", "El departamento debe pertenecer al claustro seleccionado.")
            return datos
        if not claustro:
            return datos
        existentes = ListaCandidatos.objects.filter(participacion=self.instance.participacion).exclude(pk=self.instance.pk)
        if departamento:
            existentes = existentes.filter(eleccion_claustro_departamento=departamento)
        else:
            existentes = existentes.filter(eleccion_claustro=claustro, eleccion_claustro_departamento__isnull=True)
        if existentes.exists():
            raise forms.ValidationError("El partido ya tiene una lista configurada para ese alcance.")
        return datos


class FormularioCandidato(forms.ModelForm):
    dni_elector = forms.CharField(
        label="DNI de elector vinculado",
        required=False,
        help_text="Opcional. Dejelo vacio para cargar una persona que no integra el padron.",
    )

    class Meta:
        model = Candidato
        fields = ("dni_elector", "nombre", "dni", "correo_electronico", "cargo", "tipo", "orden")

    def __init__(self, *args, lista, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.lista = lista
        self.fields["nombre"].required = False
        self.fields["dni"].required = False
        if self.instance.elector_id:
            self.fields["dni_elector"].initial = self.instance.elector.dni
        estilizar_campos(self)

    def clean(self):
        datos = super().clean()
        dni_elector = datos.get("dni_elector", "").strip()
        if not dni_elector:
            self.instance.elector = None
            return datos
        elector = Elector.objects.filter(dni=dni_elector).first()
        if elector is None:
            self.add_error("dni_elector", "No existe un elector con ese DNI.")
        else:
            self.instance.elector = elector
        return datos
