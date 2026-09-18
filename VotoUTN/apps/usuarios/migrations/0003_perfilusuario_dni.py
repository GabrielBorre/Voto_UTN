from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0002_alter_asignacionrol_mesa_alter_asignacionrol_sede_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="perfilusuario",
            name="dni",
            field=models.CharField(blank=True, max_length=12, null=True, unique=True),
        ),
    ]