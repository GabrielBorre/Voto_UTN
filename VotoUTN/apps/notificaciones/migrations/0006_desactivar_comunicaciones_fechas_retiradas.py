from django.db import migrations


CODIGOS_RETIRADOS = (
    "exhibicion-padron-provisorio",
    "publicacion-padron-definitivo",
)


def desactivar_comunicaciones(apps, schema_editor):
    Comunicacion = apps.get_model("notificaciones", "ComunicacionFechaAdministrativa")
    Comunicacion.objects.filter(
        fecha_administrativa__codigo__in=CODIGOS_RETIRADOS,
    ).update(activa=False)


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0005_destinatario_elector"),
        ("parametros", "0005_retirar_fechas_de_padron"),
    ]

    operations = [
        migrations.RunPython(desactivar_comunicaciones, migrations.RunPython.noop),
    ]
