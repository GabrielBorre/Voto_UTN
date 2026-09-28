from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0003_importacioncandidaturas_puestoeleccion_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name="partido",
                    name="numero_lista_habitual",
                ),
                migrations.RemoveField(
                    model_name="partido",
                    name="apoderado_habitual",
                ),
            ],
        ),
    ]
