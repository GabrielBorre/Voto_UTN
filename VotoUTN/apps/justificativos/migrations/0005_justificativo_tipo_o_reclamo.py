from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("justificativos", "0004_reclamo_participacion_casilla"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="tipojustificativo",
            name="es_reclamo_participacion",
        ),
        migrations.AddConstraint(
            model_name="justificativoausencia",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(reclamo_participacion=True, ausencia="votar", tipo__isnull=True)
                    | models.Q(reclamo_participacion=False, tipo__isnull=False)
                ),
                name="justificativo_tipo_o_reclamo_participacion",
            ),
        ),
    ]
