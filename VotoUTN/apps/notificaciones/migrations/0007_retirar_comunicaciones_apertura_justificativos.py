from django.db import migrations


def desactivar_comunicaciones(apps, schema_editor):
    Comunicacion = apps.get_model("notificaciones", "ComunicacionFechaAdministrativa")
    Comunicacion.objects.filter(
        fecha_administrativa__codigo="justificacion-ausencia-electoral",
    ).update(activa=False)


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0006_desactivar_comunicaciones_fechas_retiradas"),
        ("parametros", "0006_retirar_justificacion_electoral_del_calendario"),
    ]

    operations = [
        migrations.RunPython(desactivar_comunicaciones, migrations.RunPython.noop),
    ]
