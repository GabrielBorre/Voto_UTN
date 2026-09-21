import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("partidos", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="partido",
            name="numero_lista_habitual",
            field=models.CharField(
                "número de lista habitual",
                blank=True,
                help_text="Se propondrá al incorporar la agrupación a una elección; no reserva el número.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="partido",
            name="apoderado_habitual",
            field=models.CharField(
                "apoderado habitual",
                blank=True,
                help_text="Nombre de referencia; podrá cambiarse para cada elección.",
                max_length=180,
            ),
        ),
        migrations.CreateModel(
            name="OrganoElectivo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=160, unique=True)),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={"ordering": ("nombre",)},
        ),
        migrations.CreateModel(
            name="CargoElectivo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
                (
                    "organo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cargos",
                        to="partidos.organoelectivo",
                    ),
                ),
            ],
            options={"ordering": ("organo__nombre", "nombre")},
        ),
        migrations.AddConstraint(
            model_name="cargoelectivo",
            constraint=models.UniqueConstraint(fields=("organo", "nombre"), name="cargo_unico_por_organo"),
        ),
    ]
