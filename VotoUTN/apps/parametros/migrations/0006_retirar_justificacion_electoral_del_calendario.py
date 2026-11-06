from django.db import migrations


def desactivar_fecha(apps, schema_editor):
    FechaAdministrativa = apps.get_model("parametros", "FechaAdministrativa")
    FechaAdministrativa.objects.filter(codigo="justificacion-ausencia-electoral").update(
        activa=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0005_retirar_fechas_de_padron"),
    ]

    operations = [
        migrations.RunPython(desactivar_fecha, migrations.RunPython.noop),
    ]
