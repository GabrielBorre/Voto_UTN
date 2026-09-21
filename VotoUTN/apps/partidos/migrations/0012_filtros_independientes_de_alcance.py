from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0011_aclarar_alcances_del_puesto"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cargoelectivo",
            old_name="permite_claustro",
            new_name="permite_filtrar_claustros",
        ),
        migrations.RenameField(
            model_name="cargoelectivo",
            old_name="permite_departamento",
            new_name="permite_filtrar_departamentos",
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_filtrar_claustros",
            field=models.BooleanField(
                default=True,
                help_text="Permite elegir solo algunos claustros; si no se usa el filtro, se incluyen todos los de la elección.",
                verbose_name="permite limitar por claustros",
            ),
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_filtrar_departamentos",
            field=models.BooleanField(
                default=False,
                help_text="Permite elegir solo algunos departamentos; funciona independientemente del filtro por claustros.",
                verbose_name="permite limitar por departamentos",
            ),
        ),
    ]
