from django.db import migrations, models


def incorporar_tipo_reclamo(apps, schema_editor):
    tipo = apps.get_model("justificativos", "TipoJustificativo")
    tipo.objects.using(schema_editor.connection.alias).update_or_create(
        nombre="Sí voté",
        defaults={"es_reclamo_participacion": True},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("justificativos", "0002_justificativoausencia_ausencia"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipojustificativo",
            name="es_reclamo_participacion",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="justificativoausencia",
            name="comprobante_extraviado",
            field=models.BooleanField(default=False, verbose_name="Perdí el comprobante de votación"),
        ),
        migrations.RunPython(incorporar_tipo_reclamo, migrations.RunPython.noop),
    ]
