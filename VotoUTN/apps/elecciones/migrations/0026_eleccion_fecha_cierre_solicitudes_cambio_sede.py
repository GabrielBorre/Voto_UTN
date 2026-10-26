from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0025_una_eleccion_no_cerrada"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccion",
            name="fecha_cierre_solicitudes_cambio_sede",
            field=models.DateField(blank=True, null=True),
        ),
    ]
