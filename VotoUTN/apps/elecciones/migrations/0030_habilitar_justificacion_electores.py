from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0029_renombrar_estados_eleccion"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccion",
            name="justificacion_electores_habilitada_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
