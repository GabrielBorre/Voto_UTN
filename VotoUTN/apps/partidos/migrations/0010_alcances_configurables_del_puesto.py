from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0009_claustros_habilitados_por_puesto"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name="cargoelectivo",
                    name="permite_claustro",
                    field=models.BooleanField(
                        default=True,
                        help_text="Permite habilitar el puesto para un claustro completo dentro de cada elección.",
                        verbose_name="permite por claustro",
                    ),
                ),
                migrations.RemoveField(
                    model_name="cargoelectivo",
                    name="claustros_habilitados",
                ),
            ],
        ),
    ]
