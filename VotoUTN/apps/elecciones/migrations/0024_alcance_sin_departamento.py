from django.db import migrations, models
import django.db.models.deletion


def crear_alcances_sin_departamento(apps, schema_editor):
    EleccionClaustro = apps.get_model("elecciones", "EleccionClaustro")
    EleccionClaustroDepartamento = apps.get_model("elecciones", "EleccionClaustroDepartamento")
    EleccionClaustroDepartamentoSede = apps.get_model(
        "elecciones",
        "EleccionClaustroDepartamentoSede",
    )

    for eleccion_claustro in EleccionClaustro.objects.filter(
        organizacion_departamentos="sin_departamento",
    ):
        if eleccion_claustro.departamentos.filter(departamento__isnull=False).exists():
            eleccion_claustro.organizacion_departamentos = "por_departamento"
            eleccion_claustro.save(update_fields=("organizacion_departamentos",))
            continue

        alcance, _ = EleccionClaustroDepartamento.objects.get_or_create(
            eleccion_claustro=eleccion_claustro,
            departamento=None,
        )
        sedes = eleccion_claustro.sedes_habilitadas.values_list("sede_id", flat=True)
        EleccionClaustroDepartamentoSede.objects.bulk_create(
            [
                EleccionClaustroDepartamentoSede(
                    eleccion_claustro_departamento=alcance,
                    sede_id=sede_id,
                )
                for sede_id in sedes
            ],
            ignore_conflicts=True,
        )


def eliminar_alcances_sin_departamento(apps, schema_editor):
    EleccionClaustroDepartamento = apps.get_model("elecciones", "EleccionClaustroDepartamento")
    EleccionClaustroDepartamentoSede = apps.get_model(
        "elecciones",
        "EleccionClaustroDepartamentoSede",
    )
    alcances = EleccionClaustroDepartamento.objects.filter(departamento__isnull=True)
    EleccionClaustroDepartamentoSede.objects.filter(
        eleccion_claustro_departamento__in=alcances,
    ).delete()
    alcances.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0023_eleccionclaustro_organizacion_departamentos"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="eleccionclaustrodepartamento",
            name="departamento_unico_por_claustro",
        ),
        migrations.AlterField(
            model_name="eleccionclaustrodepartamento",
            name="departamento",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="elecciones_claustro_departamento",
                to="parametros.departamento",
            ),
        ),
        migrations.AddConstraint(
            model_name="eleccionclaustrodepartamento",
            constraint=models.UniqueConstraint(
                condition=models.Q(("departamento__isnull", False)),
                fields=("eleccion_claustro", "departamento"),
                name="departamento_unico_por_claustro",
            ),
        ),
        migrations.AddConstraint(
            model_name="eleccionclaustrodepartamento",
            constraint=models.UniqueConstraint(
                condition=models.Q(("departamento__isnull", True)),
                fields=("eleccion_claustro",),
                name="alcance_sin_departamento_unico_por_claustro",
            ),
        ),
        migrations.RunPython(
            crear_alcances_sin_departamento,
            eliminar_alcances_sin_departamento,
        ),
    ]
