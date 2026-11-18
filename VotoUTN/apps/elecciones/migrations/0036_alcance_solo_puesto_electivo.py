from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("elecciones", "0035_eleccion_solicitudes_cambio_sede_habilitadas_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleccionclaustrodepartamento",
            name="solo_puesto_electivo",
            field=models.BooleanField(
                default=False,
                help_text="El alcance existe solo para configurar un puesto y no participa en padrones ni mesas.",
            ),
        ),
    ]
