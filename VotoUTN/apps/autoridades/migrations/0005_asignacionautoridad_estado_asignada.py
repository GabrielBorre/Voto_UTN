from django.db import migrations, models


def normalizar_estado_asignaciones(apps, schema_editor):
    AsignacionAutoridad = apps.get_model("autoridades", "AsignacionAutoridad")
    AsignacionAutoridad.objects.filter(estado__in=("pendiente", "confirmada")).update(estado="asignada")


def restaurar_estado_anterior(apps, schema_editor):
    AsignacionAutoridad = apps.get_model("autoridades", "AsignacionAutoridad")
    AsignacionAutoridad.objects.filter(estado="asignada").update(estado="pendiente")


class Migration(migrations.Migration):

    dependencies = [
        ("autoridades", "0004_asignacionautoridad_orden_suplencia_and_more"),
    ]

    operations = [
        migrations.RunPython(normalizar_estado_asignaciones, restaurar_estado_anterior),
        migrations.AlterField(
            model_name="asignacionautoridad",
            name="estado",
            field=models.CharField(
                choices=[("asignada", "Asignada"), ("rechazada", "Rechazada")],
                default="asignada",
                max_length=16,
            ),
        ),
    ]
