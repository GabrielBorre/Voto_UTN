from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("padron", "0013_merge_20261027_1450")]

    operations = [
        migrations.AddField(
            model_name="registropadron",
            name="es_principal",
            field=models.BooleanField(default=True, verbose_name="registro principal"),
        ),
    ]
