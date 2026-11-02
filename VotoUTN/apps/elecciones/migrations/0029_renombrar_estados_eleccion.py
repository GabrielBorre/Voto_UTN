from django.db import migrations, models


ESTADOS_ANTERIORES_A_NUEVOS = {
    "borrador": "en_preparacion",
    "preparada": "publicada",
    "abierta": "en_curso",
    "cerrada": "finalizada",
}


def _renombrar(apps, schema_editor, mapa):
    Eleccion = apps.get_model("elecciones", "Eleccion")
    alias = schema_editor.connection.alias
    for anterior, nuevo in mapa.items():
        Eleccion.objects.using(alias).filter(estado=anterior).update(estado=nuevo)


def renombrar_estados(apps, schema_editor):
    _renombrar(apps, schema_editor, ESTADOS_ANTERIORES_A_NUEVOS)


def restaurar_estados(apps, schema_editor):
    _renombrar(apps, schema_editor, {nuevo: anterior for anterior, nuevo in ESTADOS_ANTERIORES_A_NUEVOS.items()})


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0028_eleccion_notificaciones_ausentes_confirmadas_en"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="eleccion", name="una_eleccion_no_cerrada"),
        migrations.AlterField(
            model_name="eleccion",
            name="estado",
            field=models.CharField(
                choices=[
                    ("en_preparacion", "En preparación"),
                    ("publicada", "Publicada"),
                    ("en_curso", "En curso"),
                    ("finalizada", "Finalizada"),
                ],
                default="en_preparacion",
                max_length=16,
            ),
        ),
        migrations.RunPython(renombrar_estados, restaurar_estados),
        migrations.AddConstraint(
            model_name="eleccion",
            constraint=models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(estado__in=("en_preparacion", "publicada", "en_curso")),
                name="una_eleccion_no_cerrada",
            ),
        ),
    ]
