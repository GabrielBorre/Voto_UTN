from django.db import migrations, models


def copiar_identificadores_a_registros(apps, schema_editor):
    RegistroPadron = apps.get_model("padron", "RegistroPadron")
    base = RegistroPadron.objects.using(schema_editor.connection.alias)
    lote = []
    for registro in base.select_related("elector").iterator(chunk_size=1000):
        registro.dni = registro.elector.dni
        registro.legajo = registro.elector.legajo
        lote.append(registro)
        if len(lote) == 1000:
            base.bulk_update(lote, ("dni", "legajo"), batch_size=1000)
            lote.clear()
    if lote:
        base.bulk_update(lote, ("dni", "legajo"), batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("padron", "0011_solicitudcambiosede"),
    ]

    operations = [
        migrations.AlterField(
            model_name="elector",
            name="dni",
            field=models.CharField(max_length=12, verbose_name="DNI"),
        ),
        migrations.AlterField(
            model_name="elector",
            name="legajo",
            field=models.CharField(max_length=20, verbose_name="legajo"),
        ),
        migrations.AddField(
            model_name="registropadron",
            name="dni",
            field=models.CharField(blank=True, editable=False, max_length=12, null=True),
        ),
        migrations.AddField(
            model_name="registropadron",
            name="legajo",
            field=models.CharField(blank=True, editable=False, max_length=20, null=True),
        ),
        migrations.RunPython(copiar_identificadores_a_registros, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="registropadron",
            name="dni",
            field=models.CharField(editable=False, max_length=12),
        ),
        migrations.AlterField(
            model_name="registropadron",
            name="legajo",
            field=models.CharField(editable=False, max_length=20),
        ),
        migrations.AddConstraint(
            model_name="registropadron",
            constraint=models.UniqueConstraint(fields=("eleccion", "dni"), name="dni_unico_por_eleccion"),
        ),
        migrations.AddConstraint(
            model_name="registropadron",
            constraint=models.UniqueConstraint(fields=("eleccion", "legajo"), name="legajo_unico_por_eleccion"),
        ),
    ]
