from django.db import migrations


class Migration(migrations.Migration):
    # En una base nueva, crear tipo_documento antes de la migración local,
    # que ya contempla la columna existente. No recrear tablas ni perder datos.
    dependencies = [
        ("padron", "0005_elector_tipo_documento"),
        ("padron", "0006_emision_padron_imprimible"),
    ]

    operations = []
