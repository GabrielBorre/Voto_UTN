from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("autoridades", "0003_turno_de_trabajo_en_autoridad"),
        ("mesas", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="mesa",
            name="turno",
        ),
    ]
