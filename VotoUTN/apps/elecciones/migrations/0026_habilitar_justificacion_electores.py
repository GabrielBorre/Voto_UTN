from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0025_una_eleccion_no_cerrada"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccion",
            name="justificacion_electores_habilitada_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
