from django.db import migrations, models


def habilitar_claustros_existentes(apps, schema_editor):
    CargoElectivo = apps.get_model("partidos", "CargoElectivo")
    Claustro = apps.get_model("parametros", "Claustro")
    claustros = list(Claustro.objects.all())
    for puesto in CargoElectivo.objects.all():
        puesto.claustros_habilitados.add(*claustros)


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0003_retirar_mensaje_embebido"),
        ("partidos", "0008_compatibilidad_columna_claustro"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargoelectivo",
            name="claustros_habilitados",
            field=models.ManyToManyField(
                help_text="Seleccione los claustros para los que puede habilitarse este puesto en una elección.",
                related_name="puestos_electivos_habilitados",
                to="parametros.claustro",
                verbose_name="claustros habilitados",
            ),
        ),
        migrations.RunPython(habilitar_claustros_existentes, migrations.RunPython.noop),
    ]
