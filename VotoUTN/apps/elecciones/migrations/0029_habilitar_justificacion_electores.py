from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0028_eleccion_notificaciones_ausentes_confirmadas_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccion",
            name="justificacion_electores_habilitada_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
