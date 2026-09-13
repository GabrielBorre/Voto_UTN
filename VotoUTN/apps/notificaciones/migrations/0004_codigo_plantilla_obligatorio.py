from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0003_preservar_mensajes_de_fechas"),
        ("parametros", "0003_retirar_mensaje_embebido"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plantillanotificacion",
            name="codigo",
            field=models.SlugField(max_length=100, unique=True),
        )
    ]
