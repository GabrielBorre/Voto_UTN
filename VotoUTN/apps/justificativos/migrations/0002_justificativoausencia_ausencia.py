from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("justificativos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="justificativoausencia",
            name="ausencia",
            field=models.CharField(
                choices=[("votar", "Ausencia a votar"), ("autoridad", "Ausencia como autoridad de mesa")],
                default="votar",
                max_length=16,
            ),
        ),
    ]
