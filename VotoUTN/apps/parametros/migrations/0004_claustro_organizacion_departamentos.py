from django.db import migrations, models


CLAUSTROS_ESTANDAR = (
    ("Docentes", "DOC", "por_departamento"),
    ("Estudiantes", "EST", "por_departamento"),
    ("Graduados", "GRAD", "por_departamento"),
    ("No docentes", "ND", "sin_departamento"),
)


def configurar_claustros_estandar(apps, schema_editor):
    Claustro = apps.get_model("parametros", "Claustro")
    for nombre, abreviatura, organizacion in CLAUSTROS_ESTANDAR:
        Claustro.objects.filter(nombre__iexact=nombre).update(
            abreviatura=abreviatura,
            organizacion_departamentos=organizacion,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0003_retirar_mensaje_embebido"),
    ]

    operations = [
        migrations.AddField(
            model_name="claustro",
            name="abreviatura",
            field=models.CharField(default="", max_length=20),
        ),
        migrations.AddField(
            model_name="claustro",
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
        migrations.RunPython(configurar_claustros_estandar, migrations.RunPython.noop),
    ]
