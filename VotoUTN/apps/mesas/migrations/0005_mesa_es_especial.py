from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mesas", "0004_asignacionmesa_autoridad_al_final")]

    operations = [
        migrations.AddField(
            model_name="mesa",
            name="es_especial",
            field=models.BooleanField(default=False, verbose_name="mesa especial"),
        ),
    ]
