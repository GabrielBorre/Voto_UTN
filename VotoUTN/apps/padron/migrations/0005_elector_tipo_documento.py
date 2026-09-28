from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("padron", "0004_merge_0002_emision_qr_0003_separar_apellido"),
    ]

    operations = [
        migrations.AddField(
            model_name="elector",
            name="tipo_documento",
            field=models.CharField(default="DNI", max_length=30, verbose_name="tipo documento"),
        ),
    ]
