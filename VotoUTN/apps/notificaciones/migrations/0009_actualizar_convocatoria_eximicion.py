from django.db import migrations


TEXTO_ANTERIOR = "Podés justificar tu imposibilidad hasta el {fecha}."
TEXTO_NUEVO = "Podés solicitar ser eximido hasta el día {fecha} inclusive."


def actualizar_convocatorias(apps, schema_editor):
    alias = schema_editor.connection.alias
    Plantilla = apps.get_model("notificaciones", "PlantillaNotificacion")
    plantillas = Plantilla.objects.using(alias).filter(
        codigo="autoridad-convocatoria-definitiva",
        contenido__contains=TEXTO_ANTERIOR,
    )
    for plantilla in plantillas.iterator():
        plantilla.contenido = plantilla.contenido.replace(TEXTO_ANTERIOR, TEXTO_NUEVO)
        plantilla.save(using=alias, update_fields=("contenido",))


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0008_actualizar_mensaje_eximicion_autoridad"),
    ]

    operations = [
        migrations.RunPython(actualizar_convocatorias, migrations.RunPython.noop),
    ]
