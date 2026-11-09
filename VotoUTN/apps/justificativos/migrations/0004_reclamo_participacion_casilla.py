from django.db import migrations, models
import django.db.models.deletion


def aplicar_restricciones_inmediatas(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def convertir_tipo_en_casilla(apps, schema_editor):
    alias = schema_editor.connection.alias
    tipo = apps.get_model("justificativos", "TipoJustificativo")
    justificativo = apps.get_model("justificativos", "JustificativoAusencia")
    reservados = tipo.objects.using(alias).filter(es_reclamo_participacion=True)
    justificativo.objects.using(alias).filter(tipo__in=reservados).update(
        reclamo_participacion=True, ausencia="votar", tipo=None,
    )
    reservados.delete()
    aplicar_restricciones_inmediatas(schema_editor)


def restaurar_tipo_reservado(apps, schema_editor):
    alias = schema_editor.connection.alias
    tipo = apps.get_model("justificativos", "TipoJustificativo")
    justificativo = apps.get_model("justificativos", "JustificativoAusencia")
    reclamos = justificativo.objects.using(alias).filter(reclamo_participacion=True)
    reservado, _ = tipo.objects.using(alias).update_or_create(
        nombre="Sí voté", defaults={"es_reclamo_participacion": True},
    )
    reclamos.update(tipo=reservado)
    aplicar_restricciones_inmediatas(schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("justificativos", "0003_reclamo_participacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="justificativoausencia",
            name="reclamo_participacion",
            field=models.BooleanField(default=False, verbose_name="Voté pero aparezco como que no lo hice"),
        ),
        migrations.AlterField(
            model_name="justificativoausencia",
            name="tipo",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="justificativos", to="justificativos.tipojustificativo",
            ),
        ),
        migrations.RunPython(convertir_tipo_en_casilla, restaurar_tipo_reservado),
    ]
