from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0012_filtros_independientes_de_alcance"),
    ]

    operations = [
        migrations.AlterField(
            model_name="candidato",
            name="elector",
            field=models.ForeignKey(
                to="padron.elector",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="candidaturas",
                null=True,
                blank=True,
                help_text="Debe integrar el padrón de la elección; se conserva nullable para candidaturas históricas.",
            ),
        ),
        migrations.AlterField(
            model_name="candidato",
            name="identificador_persona",
            field=models.CharField(
                max_length=40,
                blank=True,
                help_text="Dato histórico; no se utiliza en las nuevas candidaturas.",
            ),
        ),
    ]
