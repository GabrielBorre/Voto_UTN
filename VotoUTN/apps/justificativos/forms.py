from django import forms
from django.db import transaction
from django.utils import timezone

from apps.autoridades.models import AsignacionAutoridad
from apps.justificativos.models import JustificativoAusencia, TipoJustificativo
from apps.padron.models import RegistroPadron
from apps.justificativos.services import (
    justificativos_electorales_para_registro,
    puede_presentar_justificativo_electoral,
    registros_ausentes_de_persona,
)

class CampoMesaReclamada(forms.ModelChoiceField):
    def label_from_instance(self, registro):
        asignacion = getattr(registro, "asignacion_mesa", None)
        mesa = f"Mesa {asignacion.mesa.codigo}" if asignacion else "Sin mesa asignada"
        tipo = "principal" if registro.es_principal else "especial"
        return f"{mesa} ({tipo}) — {registro.eleccion_claustro_departamento.departamento}"


class FormularioJustificativo(forms.ModelForm):
    registro_reclamado = CampoMesaReclamada(
        label="Mesa donde votaste", queryset=RegistroPadron.objects.none(), required=False,
        empty_label="Seleccioná la mesa del comprobante",
        help_text="El reclamo corrige únicamente la ausencia de esta mesa.",
    )

    class Meta:
        model = JustificativoAusencia
        fields = ("reclamo_participacion", "registro_reclamado", "ausencia", "tipo", "detalle", "documento", "comprobante_extraviado")
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
        reclamables = registros_ausentes_de_persona(registro_padron).exclude(
            justificativos__ausencia=JustificativoAusencia.Ausencia.VOTAR,
        ).select_related(
            "eleccion", "asignacion_mesa__mesa", "eleccion_claustro_departamento__departamento",
        ).order_by("-es_principal", "pk") if registro_padron else RegistroPadron.objects.none()
        self.fields["registro_reclamado"].queryset = reclamables
        self._registros_reclamables = list(reclamables)
        if self.is_bound and self.data.get("reclamo_participacion"):
            seleccionado = self.data.get("registro_reclamado")
            elegido = next((item for item in self._registros_reclamables if str(item.pk) == str(seleccionado)), None)
            if elegido is not None:
                self.registro_padron = elegido
        if len(self._registros_reclamables) <= 1:
            self.fields["registro_reclamado"].widget = forms.HiddenInput()
        else:
            self.fields["registro_reclamado"].widget.attrs["data-requerido-reclamo"] = "true"
        if self.is_bound and not self.data.get("reclamo_participacion"):
            self.fields["registro_reclamado"].disabled = True
        self.fields["tipo"].queryset = TipoJustificativo.objects.filter(activo=True)
        self.fields["ausencia"].label = "Ausencia a justificar"
        disponibles = self.ausencias_disponibles()
        self.fields["ausencia"].choices = [
            (valor, etiqueta) for valor, etiqueta in JustificativoAusencia.Ausencia.choices
            if valor in disponibles
        ]
        self._permite_reclamo = bool(
            JustificativoAusencia.Ausencia.VOTAR in disponibles
            and self.registro_padron is not None
            and self.registro_padron.participaciones.exists()
        )
        if not self._permite_reclamo:
            for nombre in ("reclamo_participacion", "comprobante_extraviado", "registro_reclamado"):
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
        permitidas = set()
        if puede_presentar_justificativo_electoral(self.registro_padron):
            permitidas.add(JustificativoAusencia.Ausencia.VOTAR)
        eleccion = self.registro_padron.eleccion
        if (eleccion.estado == "publicada" and eleccion.autoridades_confirmadas_en
                and eleccion.fecha_limite_justificacion_autoridades and timezone.localdate() <= eleccion.fecha_limite_justificacion_autoridades
                and AsignacionAutoridad.objects.filter(registro_padron=self.registro_padron).exists()):
            permitidas.add(JustificativoAusencia.Ausencia.AUTORIDAD)
        usadas = set(
            JustificativoAusencia.objects.filter(registro_padron=self.registro_padron).values_list("ausencia", flat=True)
        )
        if justificativos_electorales_para_registro(
            registro_id=self.registro_padron.pk,
            elector_id=self.registro_padron.elector_id,
            eleccion_id=self.registro_padron.eleccion_id,
        ).exists():
            usadas.add(JustificativoAusencia.Ausencia.VOTAR)
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
            if len(self._registros_reclamables) > 1 and not datos.get("registro_reclamado"):
                self.add_error("registro_reclamado", "Indicá en qué mesa votaste para revisar su comprobante.")
            elif not datos.get("registro_reclamado") and len(self._registros_reclamables) == 1:
                self.registro_padron = self._registros_reclamables[0]
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
            from apps.elecciones.models import Eleccion
            with transaction.atomic():
                eleccion = Eleccion.objects.select_for_update().get(pk=self.registro_padron.eleccion_id)
                self.registro_padron.eleccion = eleccion
                if justificativo.ausencia not in self.ausencias_disponibles():
                    raise forms.ValidationError("La ausencia ya fue presentada o su presentación no está habilitada.")
                if justificativo.reclamo_participacion and not self.registro_padron.participaciones.exists():
                    raise forms.ValidationError("La ausencia de la mesa reclamada ya no está registrada.")
                if justificativo.ausencia == JustificativoAusencia.Ausencia.AUTORIDAD and (eleccion.estado != Eleccion.Estado.PUBLICADA or not eleccion.autoridades_confirmadas_en or not eleccion.fecha_limite_justificacion_autoridades or timezone.localdate() > eleccion.fecha_limite_justificacion_autoridades):
                    raise forms.ValidationError("La presentación de justificativos de autoridades no está habilitada o su plazo venció.")
                if justificativo.ausencia == JustificativoAusencia.Ausencia.VOTAR and not justificativo.reclamo_participacion:
                    justificativo.registro_padron = registros_ausentes_de_persona(
                        self.registro_padron,
                    ).order_by("-es_principal", "pk").first()
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
