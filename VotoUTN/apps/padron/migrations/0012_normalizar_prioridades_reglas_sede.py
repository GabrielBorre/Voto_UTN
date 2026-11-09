from django.db import migrations


def normalizar_prioridades(apps, schema_editor):
    ReglaSedeClaustro = apps.get_model("padron", "ReglaSedeClaustro")
    ConfiguracionSedesClaustro = apps.get_model("padron", "ConfiguracionSedesClaustro")
    base = ReglaSedeClaustro.objects.using(schema_editor.connection.alias)

    for configuracion_id in ConfiguracionSedesClaustro.objects.using(
        schema_editor.connection.alias
    ).values_list("id", flat=True):
        reglas = base.filter(configuracion_id=configuracion_id).order_by("orden", "id")
        for prioridad, regla in enumerate(reglas, start=1):
            if regla.orden != prioridad:
                base.filter(pk=regla.pk).update(orden=prioridad)


class Migration(migrations.Migration):
    dependencies = [
        ("padron", "0011_merge_20261015_0025"),
    ]

    operations = [
        migrations.RunPython(normalizar_prioridades, migrations.RunPython.noop),
    ]
