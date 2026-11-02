from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0027_alter_eleccion_estado"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccion",
            name="notificaciones_ausentes_confirmadas_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
