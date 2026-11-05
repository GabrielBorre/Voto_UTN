from django.db import migrations


CODIGOS_RETIRADOS = (
    "exhibicion-padron-provisorio",
    "publicacion-padron-definitivo",
)


def desactivar_fechas(apps, schema_editor):
    FechaAdministrativa = apps.get_model("parametros", "FechaAdministrativa")
    FechaAdministrativa.objects.filter(codigo__in=CODIGOS_RETIRADOS).update(activa=False)


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0004_claustro_organizacion_departamentos"),
    ]

    operations = [
        migrations.RunPython(desactivar_fechas, migrations.RunPython.noop),
    ]
