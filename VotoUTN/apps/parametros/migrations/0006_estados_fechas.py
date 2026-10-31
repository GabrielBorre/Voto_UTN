from django.db import migrations


def asignar(apps, schema_editor):
    Fecha = apps.get_model("parametros", "FechaAdministrativa")
    Variante = apps.get_model("notificaciones", "VarianteComunicacionFechaAdministrativa")
    alias = schema_editor.connection.alias
    for fecha in Fecha.objects.using(alias).all():
        fecha.estado_eleccion = "en_curso" if fecha.codigo in ("justificacion-ausencia-electoral", "justificacion-ausencia-autoridad") else "publicada"
        variantes = Variante.objects.using(alias).filter(comunicacion__fecha_administrativa=fecha, activa=True, plantilla__activa=True).order_by("comunicacion__orden", "prioridad")
        principal = variantes.first()
        recordatorio = variantes.exclude(comunicacion_id=principal.comunicacion_id).first() if principal else None
        fecha.plantilla_mensaje_id = principal.plantilla_id if principal else None
        fecha.plantilla_recordatorio_id = recordatorio.plantilla_id if recordatorio else None
        fecha.envia_mensaje = principal is not None
        fecha.permite_recordatorios = recordatorio is not None
        fecha.save(using=alias)


class Migration(migrations.Migration):
    dependencies = [("parametros", "0005_fechaadministrativa_envia_mensaje_and_more")]
    operations = [migrations.RunPython(asignar, migrations.RunPython.noop)]
