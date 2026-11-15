from django.db import migrations, models


def asociar_puestos_existentes_a_sus_claustros_configurados(apps, schema_editor):
    CargoElectivo = apps.get_model("partidos", "CargoElectivo")
    PuestoEleccion = apps.get_model("partidos", "PuestoEleccion")
    Claustro = apps.get_model("parametros", "Claustro")
    alias = schema_editor.connection.alias
    for puesto in CargoElectivo.objects.using(alias).all():
        claustro_ids = PuestoEleccion.objects.using(alias).filter(
            puesto_id=puesto.pk,
        ).values_list("eleccion_claustro__claustro_id", flat=True).distinct()
        claustros = Claustro.objects.using(alias).filter(pk__in=claustro_ids)
        puesto.claustros_habilitados.set(claustros)


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0004_claustro_organizacion_departamentos"),
        ("partidos", "0013_aclarar_padron_obligatorio_candidatos"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name="cargoelectivo",
                    name="claustros_habilitados",
                    field=models.ManyToManyField(
                        blank=True,
                        help_text="Claustros para los que puede utilizarse este puesto.",
                        related_name="puestos_electivos_habilitados",
                        to="parametros.claustro",
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            asociar_puestos_existentes_a_sus_claustros_configurados,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_filtrar_claustros",
            field=models.BooleanField(
                default=True,
                help_text="Permite elegir un subconjunto de los claustros asociados; sin filtro se incluyen todos los asociados presentes en la elección.",
                verbose_name="permite limitar por claustros",
            ),
        ),
    ]
