from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("padron", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="registropadron",
            name="numero_mesa_qr",
            field=models.PositiveIntegerField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="registropadron",
            name="qr_generado_en",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
