from django import forms
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo

class FormularioJustificativo(forms.ModelForm):
    class Meta:
        model = JustificativoAusencia
        fields = ("reclamo_participacion", "ausencia", "tipo", "detalle", "documento", "comprobante_extraviado")
        labels = {"detalle": "Comentario", "documento": "Documentación o comprobante de votación"}
        help_texts = {
            "reclamo_participacion": (
                "Marcá esta opción si votaste y figurás como ausente. No hace falta elegir ausencia ni tipo; "
                "adjuntá el comprobante y la Junta revisará el padrón."
            ),
            "comprobante_extraviado": (
                "Marcá esta opción si no podés adjuntar el comprobante de votación e indicá su pérdida en el comentario."
            ),
        }
        widgets = {"detalle": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, registro_padron=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.registro_padron = registro_padron
        self.fields["tipo"].queryset = TipoJustificativo.objects.filter(activo=True)
        self.fields["ausencia"].label = "Ausencia a justificar"
        disponibles = self.ausencias_disponibles()
        self.fields["ausencia"].choices = [
            (valor, etiqueta) for valor, etiqueta in JustificativoAusencia.Ausencia.choices
            if valor in disponibles
        ]
        self._permite_reclamo = bool(
            JustificativoAusencia.Ausencia.VOTAR in disponibles
            and registro_padron is not None
            and registro_padron.participaciones.exists()
        )
        if not self._permite_reclamo:
            for nombre in ("reclamo_participacion", "comprobante_extraviado"):
                self.fields[nombre].disabled = True
                self.fields[nombre].widget = forms.HiddenInput()
        # Se validan en clean() porque dependen de la casilla de reclamo.
        self.fields["ausencia"].required = False
        self.fields["tipo"].required = False
        for nombre, campo in self.fields.items():
            es_casilla = isinstance(campo.widget, forms.CheckboxInput)
            campo.widget.attrs.setdefault("class", "form-check-input" if es_casilla else "form-control")
            if es_casilla and campo.help_text:
                campo.widget.attrs["aria-describedby"] = f"ayuda_{nombre}"

    def permite_reclamo(self):
        return self._permite_reclamo

    def es_reclamo(self):
        return self.permite_reclamo() and bool(self.cleaned_data.get("reclamo_participacion"))

    def plazo_autoridad_vencido(self):
        limite = self.registro_padron.eleccion.fecha_limite_justificacion_autoridades if self.registro_padron else None
        return bool(limite and timezone.localdate() > limite)

    def ausencias_disponibles(self):
        if self.registro_padron is None:
            return set()
        permitidas = {JustificativoAusencia.Ausencia.VOTAR}
        if not self.plazo_autoridad_vencido() and AsignacionAutoridad.objects.filter(registro_padron=self.registro_padron).exists():
            permitidas.add(JustificativoAusencia.Ausencia.AUTORIDAD)
        usadas = set(
            JustificativoAusencia.objects.filter(registro_padron=self.registro_padron).values_list("ausencia", flat=True)
        )
        return permitidas - usadas

    def clean(self):
        datos = super().clean()
        if self.registro_padron is None:
            raise forms.ValidationError("No existe un padrón activo para presentar el justificativo.")
        if not self.ausencias_disponibles():
            raise forms.ValidationError("Ya presentó el máximo de justificativos permitidos.")
        tipo = datos.get("tipo")
        extraviado = datos.get("comprobante_extraviado", False)
        if self.es_reclamo():
            for nombre in ("ausencia", "tipo"):
                self._errors.pop(nombre, None)
            datos["ausencia"] = JustificativoAusencia.Ausencia.VOTAR
            datos["tipo"] = None
            if not datos.get("documento") and not extraviado:
                self.add_error("documento", "Adjuntá el comprobante o indicá que lo perdiste y explicalo en el comentario.")
        else:
            datos["comprobante_extraviado"] = False
            if not datos.get("ausencia"):
                self.add_error("ausencia", "Este campo es obligatorio.")
            if not tipo:
                self.add_error("tipo", "Este campo es obligatorio.")
        if self.plazo_autoridad_vencido() and datos.get("ausencia") == JustificativoAusencia.Ausencia.AUTORIDAD:
            self.add_error("ausencia", "Venció el plazo para justificar la inasistencia como autoridad de mesa.")
        return datos

    def save(self, commit=True):
        justificativo = super().save(commit=False)
        justificativo.registro_padron = self.registro_padron
        if commit:
            justificativo.save()
            self.save_m2m()
        return justificativo

    def clean_documento(self):
        documento = self.cleaned_data.get("documento")
        if documento is None:
            return documento
        extensiones = (".pdf", ".jpg", ".jpeg", ".png")
        if not documento.name.lower().endswith(extensiones) or documento.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Adjunte un PDF o imagen de hasta 5 MB.")
        return documento


class FormularioResolucionJustificativo(forms.Form):
    estado = forms.ChoiceField(
        label="Resolución",
        choices=(
            (JustificativoAusencia.Estado.APROBADO, "Aprobar"),
            (JustificativoAusencia.Estado.RECHAZADO, "Rechazar"),
        ),
    )
    observacion_resolucion = forms.CharField(
        label="Observación de la resolución",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
