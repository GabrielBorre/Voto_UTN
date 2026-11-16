"""Evita la unicidad transitoria sobre registros departamentales adicionales.

Las bases que aún no aplicaron la rama de identidad usan esta ruta después
de habilitar los registros adicionales. Django conserva la ruta original para
bases que ya aplicaron una parte de las migraciones reemplazadas.
"""
from django.db import migrations, models


def copiar_identificadores(apps, schema_editor):
    RegistroPadron = apps.get_model("padron", "RegistroPadron")
    registros = RegistroPadron.objects.using(schema_editor.connection.alias)
    lote = []
    for registro in registros.select_related("elector").iterator(chunk_size=1000):
        registro.dni = registro.elector.dni
        registro.legajo = registro.elector.legajo
        lote.append(registro)
        if len(lote) == 1000:
            registros.bulk_update(lote, ("dni", "legajo"), batch_size=1000)
            lote.clear()
    if lote:
        registros.bulk_update(lote, ("dni", "legajo"), batch_size=1000)


class Migration(migrations.Migration):
    replaces = [
        ("padron", "0012_identidad_electoral_por_eleccion"),
        ("padron", "0014_unir_ramas_identidad_y_prioridades"),
        ("padron", "0016_merge_20261115_1910"),
        ("padron", "0017_remove_registropadron_dni_unico_por_eleccion_and_more"),
    ]

    dependencies = [
        ("padron", "0015_registros_por_departamento"),
        ("elecciones", "0034_merge_autoridades_justificacion"),
        ("parametros", "0004_claustro_organizacion_departamentos"),
    ]

    operations = [
        migrations.AlterField("elector", "dni", models.CharField(max_length=12, verbose_name="DNI")),
        migrations.AlterField("elector", "legajo", models.CharField(max_length=20, verbose_name="legajo")),
        migrations.AddField("registropadron", "dni", models.CharField(blank=True, editable=False, max_length=12, null=True)),
        migrations.AddField("registropadron", "legajo", models.CharField(blank=True, editable=False, max_length=20, null=True)),
        migrations.RunPython(copiar_identificadores, migrations.RunPython.noop),
        migrations.AlterField("registropadron", "dni", models.CharField(editable=False, max_length=12)),
        migrations.AlterField("registropadron", "legajo", models.CharField(editable=False, max_length=20)),
        migrations.AddConstraint(
            "registropadron",
            models.UniqueConstraint(fields=("eleccion", "dni"), condition=models.Q(es_principal=True), name="dni_unico_por_eleccion"),
        ),
        migrations.AddConstraint(
            "registropadron",
            models.UniqueConstraint(fields=("eleccion", "legajo"), condition=models.Q(es_principal=True), name="legajo_unico_por_eleccion"),
        ),
    ]
