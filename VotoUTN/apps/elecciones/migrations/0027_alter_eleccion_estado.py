from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0026_eleccion_fecha_cierre_solicitudes_cambio_sede"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eleccion",
            name="estado",
            field=models.CharField(
                choices=[
                    ("borrador", "En preparación"),
                    ("preparada", "Publicada"),
                    ("abierta", "En curso"),
                    ("cerrada", "Finalizada"),
                ],
                default="borrador",
                max_length=16,
            ),
        ),
    ]
