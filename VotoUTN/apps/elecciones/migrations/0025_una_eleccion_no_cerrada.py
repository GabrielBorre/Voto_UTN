from django.db import migrations, models


def validar_unica_eleccion_no_cerrada(apps, schema_editor):
    Eleccion = apps.get_model("elecciones", "Eleccion")
    alias = schema_editor.connection.alias
    elecciones = list(
        Eleccion.objects.using(alias)
        .filter(estado__in=("borrador", "preparada", "abierta"))
        .order_by("id")
        .values_list("id", "estado")
    )
    if len(elecciones) > 1:
        detalle = ", ".join(f"{identificador} ({estado})" for identificador, estado in elecciones)
        raise RuntimeError(
            "No se puede aplicar la restricción: hay más de una elección sin cerrar "
            f"({detalle}). Cierre manualmente las elecciones excedentes y vuelva a ejecutar las migraciones."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0024_alcance_sin_departamento"),
    ]

    operations = [
        migrations.RunPython(validar_unica_eleccion_no_cerrada, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="eleccion",
            constraint=models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(estado__in=("borrador", "preparada", "abierta")),
                name="una_eleccion_no_cerrada",
            ),
        ),
    ]