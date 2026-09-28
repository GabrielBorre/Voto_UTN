import django.db.models.deletion
from django.db import migrations, models


def copiar_turnos_a_claustros(apps, schema_editor):
    EleccionTurno = apps.get_model("elecciones", "EleccionTurno")
    EleccionClaustro = apps.get_model("elecciones", "EleccionClaustro")
    EleccionClaustroTurno = apps.get_model("elecciones", "EleccionClaustroTurno")

    relaciones = []
    for eleccion_turno in EleccionTurno.objects.all().iterator():
        claustros = EleccionClaustro.objects.filter(
            eleccion_id=eleccion_turno.eleccion_id,
        ).values_list("id", flat=True)
        relaciones.extend(
            EleccionClaustroTurno(
                eleccion_claustro_id=eleccion_claustro_id,
                turno_id=eleccion_turno.turno_id,
            )
            for eleccion_claustro_id in claustros
        )
    EleccionClaustroTurno.objects.bulk_create(relaciones, ignore_conflicts=True)


def restaurar_turnos_globales(apps, schema_editor):
    EleccionTurno = apps.get_model("elecciones", "EleccionTurno")
    EleccionClaustroTurno = apps.get_model("elecciones", "EleccionClaustroTurno")

    relaciones = {
        (relacion.eleccion_claustro.eleccion_id, relacion.turno_id)
        for relacion in EleccionClaustroTurno.objects.select_related("eleccion_claustro").all()
    }
    EleccionTurno.objects.bulk_create(
        [
            EleccionTurno(eleccion_id=eleccion_id, turno_id=turno_id)
            for eleccion_id, turno_id in relaciones
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("autoridades", "0003_turno_de_trabajo_en_autoridad"),
        ("elecciones", "0021_fechas_de_eleccion_sin_hora"),
        ("parametros", "0003_retirar_mensaje_embebido"),
    ]

    operations = [
        migrations.CreateModel(
            name="EleccionClaustroTurno",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "eleccion_claustro",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="turnos_autoridad",
                        to="elecciones.eleccionclaustro",
                    ),
                ),
                (
                    "turno",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="elecciones_turno",
                        to="parametros.turno",
                    ),
                ),
            ],
        ),
        migrations.RunPython(copiar_turnos_a_claustros, restaurar_turnos_globales),
        migrations.DeleteModel(name="EleccionTurno"),
        migrations.AddConstraint(
            model_name="eleccionclaustroturno",
            constraint=models.UniqueConstraint(
                fields=("eleccion_claustro", "turno"),
                name="turno_unico_por_claustro",
            ),
        ),
    ]
