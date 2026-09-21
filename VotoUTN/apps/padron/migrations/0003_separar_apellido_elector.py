from django.db import migrations, models


def separar_apellidos(apps, schema_editor):
    Elector = apps.get_model("padron", "Elector")
    for elector in Elector.objects.all().iterator():
        partes = (elector.nombre or "").split()
        if len(partes) < 2:
            continue
        elector.nombre = " ".join(partes[:-1])
        elector.apellido = partes[-1]
        elector.save(update_fields=("nombre", "apellido"))


class Migration(migrations.Migration):
    dependencies = [
        ("padron", "0002_add_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="elector",
            name="apellido",
            field=models.CharField(blank=True, max_length=180, verbose_name="apellido"),
        ),
        migrations.RunPython(separar_apellidos, migrations.RunPython.noop),
    ]