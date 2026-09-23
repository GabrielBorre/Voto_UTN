import django.db.models.deletion
from django.db import migrations, models


def asignar_turno_historico(apps, schema_editor):
    AsignacionAutoridad = apps.get_model("autoridades", "AsignacionAutoridad")
    EleccionTurno = apps.get_model("elecciones", "EleccionTurno")

    for asignacion in AsignacionAutoridad.objects.select_related("mesa").all():
        turno_id = asignacion.mesa.turno_id
        if turno_id is None:
            turno_id = (
                EleccionTurno.objects.filter(eleccion_id=asignacion.mesa.eleccion_id)
                .order_by("turno__hora_inicio", "turno__nombre")
                .values_list("turno_id", flat=True)
                .first()
            )
        if turno_id is None:
            raise RuntimeError(
                "No se puede migrar una autoridad sin un turno histórico o un turno habilitado en su elección."
            )
        AsignacionAutoridad.objects.filter(pk=asignacion.pk).update(turno_id=turno_id)


def restaurar_turno_en_mesa(apps, schema_editor):
    AsignacionAutoridad = apps.get_model("autoridades", "AsignacionAutoridad")
    Mesa = apps.get_model("mesas", "Mesa")

    for asignacion in AsignacionAutoridad.objects.exclude(turno_id=None).order_by("pk"):
        Mesa.objects.filter(pk=asignacion.mesa_id, turno_id=None).update(turno_id=asignacion.turno_id)


class Migration(migrations.Migration):
    dependencies = [
        ("autoridades", "0002_initial"),
        ("elecciones", "0021_fechas_de_eleccion_sin_hora"),
        ("mesas", "0001_initial"),
        ("parametros", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="asignacionautoridad",
            name="turno",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="asignaciones_autoridad",
                to="parametros.turno",
            ),
        ),
        migrations.RunPython(asignar_turno_historico, restaurar_turno_en_mesa),
        migrations.AlterField(
            model_name="asignacionautoridad",
            name="turno",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="asignaciones_autoridad",
                to="parametros.turno",
            ),
        ),
    ]
