from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0005_compatibilidad_columnas_habituales"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargoelectivo",
            name="permite_claustro",
            field=models.BooleanField(
                default=True,
                help_text="Permite habilitar el puesto para todo un claustro, sin distinguir departamento.",
                verbose_name="permite por claustro",
            ),
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_departamento",
            field=models.BooleanField(
                default=False,
                help_text="Permite habilitar el puesto para un departamento concreto dentro del claustro.",
                verbose_name="permite por departamento",
            ),
        ),
    ]
