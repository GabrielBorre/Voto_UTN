from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0010_alcances_configurables_del_puesto"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_claustro",
            field=models.BooleanField(
                default=True,
                help_text="En la elección se eligen uno o varios claustros concretos y el puesto abarca cada uno sin limitar departamentos.",
                verbose_name="permite alcance sin filtro por departamento",
            ),
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_departamento",
            field=models.BooleanField(
                default=False,
                help_text="Permite elegir claustros concretos y restringir el alcance a uno o varios de sus departamentos.",
                verbose_name="permite restringir por departamento",
            ),
        ),
    ]
