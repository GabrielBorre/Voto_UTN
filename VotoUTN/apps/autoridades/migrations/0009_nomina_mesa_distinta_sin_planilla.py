from django.db import migrations, models


def normalizar_modos_historicos(apps, schema_editor):
    ConfiguracionAutoridades = apps.get_model("autoridades", "ConfiguracionAutoridades")
    ConfiguracionAutoridades.objects.filter(modo__in=("planilla", "manual")).update(modo="aleatorio")


class Migration(migrations.Migration):

    dependencies = [
        ("autoridades", "0008_alter_configuracionautoridades_modo"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracionautoridades",
            name="permitir_mesa_distinta",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(normalizar_modos_historicos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="configuracionautoridades",
            name="modo",
            field=models.CharField(
                choices=[
                    ("nomina", "Nómina común"),
                    ("aleatorio", "Sorteo por mesa"),
                ],
                default="nomina",
                max_length=12,
            ),
        ),
    ]
