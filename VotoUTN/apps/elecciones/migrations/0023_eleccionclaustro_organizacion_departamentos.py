from django.db import migrations, models


def copiar_organizacion_del_parametro(apps, schema_editor):
    EleccionClaustro = apps.get_model("elecciones", "EleccionClaustro")
    relaciones = list(EleccionClaustro.objects.select_related("claustro"))
    for relacion in relaciones:
        relacion.organizacion_departamentos = relacion.claustro.organizacion_departamentos
    EleccionClaustro.objects.bulk_update(relaciones, ("organizacion_departamentos",))


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0022_turnos_autoridades_por_claustro"),
        ("parametros", "0004_claustro_organizacion_departamentos"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccionclaustro",
            name="organizacion_departamentos",
            field=models.CharField(
                choices=[
                    ("por_departamento", "Por departamentos"),
                    ("sin_departamento", "Sin distinción por departamento"),
                ],
                default="por_departamento",
                max_length=24,
            ),
        ),
        migrations.RunPython(copiar_organizacion_del_parametro, migrations.RunPython.noop),
    ]
