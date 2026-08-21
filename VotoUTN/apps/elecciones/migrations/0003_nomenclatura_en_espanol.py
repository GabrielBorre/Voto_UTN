from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("elecciones", "0002_mesa_votante_mesa_mesa_unique_mesa_per_eleccion"),
    ]

    operations = [
        migrations.RenameField(
            model_name="eleccion",
            old_name="name",
            new_name="nombre",
        ),
        migrations.RenameField(
            model_name="eleccion",
            old_name="starts_at",
            new_name="fecha_inicio",
        ),
        migrations.RenameField(
            model_name="eleccion",
            old_name="ends_at",
            new_name="fecha_fin",
        ),
        migrations.RenameField(
            model_name="eleccion",
            old_name="is_active",
            new_name="habilitada",
        ),
        migrations.RenameModel(
            old_name="Votante",
            new_name="Elector",
        ),
        migrations.RenameField(
            model_name="elector",
            old_name="name",
            new_name="nombre",
        ),
        migrations.AlterModelOptions(
            name="eleccion",
            options={"ordering": ["-fecha_inicio"]},
        ),
        migrations.AlterField(
            model_name="elector",
            name="mesa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="electores",
                to="elecciones.mesa",
                verbose_name="mesa",
            ),
        ),
    ]
