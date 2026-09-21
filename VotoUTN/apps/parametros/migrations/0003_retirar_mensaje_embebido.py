from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0002_catalogo_fechas_reutilizables"),
        ("notificaciones", "0003_preservar_mensajes_de_fechas"),
    ]

    operations = [
        migrations.RemoveField(model_name="fechaadministrativa", name="asunto_notificacion"),
        migrations.RemoveField(model_name="fechaadministrativa", name="mensaje_notificacion"),
        migrations.AlterField(
            model_name="fechaadministrativa",
            name="codigo",
            field=models.SlugField(max_length=80, unique=True),
        ),
    ]
