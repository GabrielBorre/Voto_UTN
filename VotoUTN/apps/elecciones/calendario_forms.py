from datetime import timedelta
from django import forms
from django.forms import BaseModelFormSet, modelformset_factory
from django.db.models import Q
from django.utils import timezone
from apps.parametros.models import FechaAdministrativa
from apps.notificaciones.models import MensajeProgramado, PlantillaNotificacion


class FormularioMensajeProgramado(forms.ModelForm):
    class Meta:
        model = MensajeProgramado
        fields = ("fecha_administrativa", "recordatorio", "plantilla", "programado_para", "habilitado")
        widgets = {"programado_para": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})}

    def __init__(self, *args, estado, **kwargs):
        super().__init__(*args, **kwargs)
        self.estado = estado
        self.fields["fecha_administrativa"].queryset = FechaAdministrativa.objects.filter(Q(activa=True, estado_eleccion=estado) | Q(pk=self.instance.fecha_administrativa_id))
        self.fields["plantilla"].queryset = PlantillaNotificacion.objects.filter(Q(activa=True) | Q(pk=self.instance.plantilla_id)).exclude(categoria="transaccional")
        self.fields["programado_para"].widget.attrs["min"] = (timezone.localdate() + timedelta(days=1)).isoformat() + "T00:00"
        self.fields["programado_para"].label = "Fecha y hora del envío"
        self.fields["habilitado"].label = "Enviar mensaje"

    def clean(self):
        datos = super().clean()
        if not datos.get("habilitado"):
            return datos
        fecha = datos.get("fecha_administrativa")
        plantilla = datos.get("plantilla")
        momento = datos.get("programado_para")
        if momento and (not self.instance.pk or self.has_changed()):
            if timezone.localtime(momento).date() <= timezone.localdate():
                self.add_error("programado_para", "El envío debe programarse para mañana o después.")
        if fecha:
            if not fecha.activa or fecha.estado_eleccion != self.estado:
                self.add_error("fecha_administrativa", "La fecha debe estar activa y pertenecer a este estado.")
            if datos.get("recordatorio") and not fecha.permite_recordatorios:
                self.add_error("recordatorio", "Esta fecha no permite recordatorios.")
            elif not datos.get("recordatorio") and not fecha.envia_mensaje:
                self.add_error("fecha_administrativa", "Esta fecha no permite un mensaje principal.")
            if plantilla and not set(plantilla.roles_destinatarios).issubset(fecha.roles_destinatarios):
                self.add_error("plantilla", "La plantilla no puede ampliar los destinatarios de la fecha.")
        if plantilla and not plantilla.activa:
            self.add_error("plantilla", "La plantilla debe estar activa.")
        return datos


class ConjuntoMensajes(BaseModelFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        esperados = set(self.queryset.values_list("pk", flat=True))
        recibidos = [form.cleaned_data.get("id").pk for form in self.forms if form.cleaned_data.get("id")]
        if set(recibidos) != esperados or len(recibidos) != len(esperados) or self.initial_form_count() != len(esperados):
            raise forms.ValidationError("El calendario cambió. Recargue la página antes de guardar.")
        principales = set()
        for formulario in self.forms:
            datos = formulario.cleaned_data
            identificador = datos.get("id")
            if identificador and not self.queryset.filter(pk=identificador.pk).exists():
                raise forms.ValidationError("El mensaje ya fue procesado o no pertenece a este calendario.")
            if not datos or not datos.get("habilitado") or datos.get("DELETE"):
                continue
            if not datos.get("recordatorio"):
                clave = datos["fecha_administrativa"].pk
                if clave in principales:
                    raise forms.ValidationError("Solo puede haber un mensaje principal por fecha; agregue recordatorios para los demás envíos.")
                principales.add(clave)


def formulario_calendario(eleccion, estado, datos=None):
    definiciones = list(FechaAdministrativa.objects.filter(activa=True, estado_eleccion=estado))
    pendientes = eleccion.mensajes_programados.filter(estado_eleccion=estado, procesado_en__isnull=True)
    existentes = set(eleccion.mensajes_programados.filter(estado_eleccion=estado).values_list("fecha_administrativa_id", flat=True))
    iniciales = [{"fecha_administrativa": fecha.pk, "plantilla": fecha.plantilla_mensaje_id or fecha.plantilla_recordatorio_id,
                  "recordatorio": not fecha.envia_mensaje, "habilitado": False}
                 for fecha in definiciones if fecha.pk not in existentes and (fecha.envia_mensaje or fecha.permite_recordatorios)]
    conjunto = modelformset_factory(MensajeProgramado, form=FormularioMensajeProgramado, formset=ConjuntoMensajes, extra=max(1, len(iniciales)), can_delete=True)
    formulario = conjunto(datos, queryset=pendientes, initial=iniciales, form_kwargs={"estado": estado}, prefix="mensajes")
    formulario.definiciones = definiciones
    formulario.plantillas_sugeridas = {str(fecha.pk): {"principal": fecha.plantilla_mensaje_id, "recordatorio": fecha.plantilla_recordatorio_id} for fecha in definiciones}
    return formulario


def guardar_calendario(formulario, eleccion, estado):
    for objeto in formulario.save(commit=False):
        objeto.eleccion = eleccion
        objeto.estado_eleccion = estado
        objeto.save()
    for objeto in formulario.deleted_objects:
        objeto.habilitado = False
        objeto.save(update_fields=("habilitado",))
