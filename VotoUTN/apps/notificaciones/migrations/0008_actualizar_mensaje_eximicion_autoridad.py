from django.db import migrations


TEXTO_ANTERIOR = (
    "Se actualizó la fecha límite para justificar una inasistencia como autoridad de mesa en "
)
TEXTO_NUEVO = (
    "Se actualizó la fecha límite para solicitar ser eximido de la función de autoridad de mesa en "
)


def actualizar_mensajes(apps, schema_editor):
    alias = schema_editor.connection.alias
    Plantilla = apps.get_model("notificaciones", "PlantillaNotificacion")
    Envio = apps.get_model("notificaciones", "EnvioNotificacion")

    plantillas = Plantilla.objects.using(alias).filter(
        codigo="autoridad-plazo-eximicion-modificado",
        contenido__contains=TEXTO_ANTERIOR,
    )
    for plantilla in plantillas.iterator():
        plantilla.contenido = plantilla.contenido.replace(TEXTO_ANTERIOR, TEXTO_NUEVO)
        plantilla.save(using=alias, update_fields=("contenido",))

    envios = Envio.objects.using(alias).filter(
        plantilla__codigo="autoridad-plazo-eximicion-modificado",
        contenido__contains=TEXTO_ANTERIOR,
    )
    for envio in envios.iterator():
        envio.contenido = envio.contenido.replace(TEXTO_ANTERIOR, TEXTO_NUEVO)
        envio.save(using=alias, update_fields=("contenido",))


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0007_retirar_comunicaciones_apertura_justificativos"),
    ]

    operations = [
        migrations.RunPython(actualizar_mensajes, migrations.RunPython.noop),
    ]
