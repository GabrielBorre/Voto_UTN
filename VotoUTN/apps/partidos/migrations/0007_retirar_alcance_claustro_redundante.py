from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0006_alcances_permitidos_por_puesto"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name="cargoelectivo",
                    name="permite_claustro",
                ),
            ],
        ),
    ]
