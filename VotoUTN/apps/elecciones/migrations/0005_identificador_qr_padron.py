import uuid

from django.db import migrations, models


def asignar_identificadores_qr(apps, schema_editor):
    RegistroPadron = apps.get_model("elecciones", "RegistroPadron")
    for registro in RegistroPadron.objects.filter(identificador_qr__isnull=True).iterator():
        registro.identificador_qr = uuid.uuid4()
        registro.save(update_fields=("identificador_qr",))


class Migration(migrations.Migration):
    dependencies = [("elecciones", "0004_modelo_electoral_base")]

    operations = [
        migrations.AddField(
            model_name="registropadron",
            name="identificador_qr",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(asignar_identificadores_qr, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="registropadron",
            name="identificador_qr",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
