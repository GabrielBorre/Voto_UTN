import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("padron", "0005_padrones_votacion"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmisionPadronImprimible",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado", models.CharField(choices=[("vigente", "Vigente"), ("invalidada", "Invalidada")], default="vigente", max_length=12)),
                ("emitida_en", models.DateTimeField(auto_now_add=True)),
                ("invalidada_en", models.DateTimeField(blank=True, null=True)),
                ("motivo_invalidacion", models.CharField(blank=True, max_length=500)),
                ("eleccion_claustro", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="emisiones_padron", to="elecciones.eleccionclaustro")),
                ("emitida_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="emisiones_padron_realizadas", to=settings.AUTH_USER_MODEL)),
                ("invalidada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="emisiones_padron_invalidadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-emitida_en",)},
        ),
        migrations.AddConstraint(
            model_name="emisionpadronimprimible",
            constraint=models.UniqueConstraint(condition=models.Q(estado="vigente"), fields=("eleccion_claustro",), name="emision_vigente_unica_por_claustro"),
        ),
    ]
