import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def crear_cupos_desde_puestos_existentes(apps, schema_editor):
    """Conserva las cantidades ya configuradas; sin antecedentes usa un titular y un suplente."""
    CargoElectivo = apps.get_model("partidos", "CargoElectivo")
    CupoPuestoClaustro = apps.get_model("partidos", "CupoPuestoClaustro")
    PuestoEleccion = apps.get_model("partidos", "PuestoEleccion")
    alias = schema_editor.connection.alias
    for cargo in CargoElectivo.objects.using(alias).all():
        for claustro in cargo.claustros_habilitados.all():
            existente = PuestoEleccion.objects.using(alias).filter(
                puesto_id=cargo.pk, eleccion_claustro__claustro_id=claustro.pk,
            ).order_by("-id").first()
            CupoPuestoClaustro.objects.using(alias).get_or_create(
                puesto_id=cargo.pk,
                claustro_id=claustro.pk,
                defaults={
                    "cantidad_titulares": max(1, existente.cantidad_titulares) if existente else 1,
                    "cantidad_suplentes": max(1, existente.cantidad_suplentes) if existente else 1,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("parametros", "0006_retirar_justificacion_electoral_del_calendario"),
        ("partidos", "0014_asociar_puestos_a_claustros"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargoelectivo",
            name="departamento",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Opcional, para puestos departamentales. Si se indica, el puesto se genera solo para ese "
                    "departamento y los demás puestos departamentales lo omiten."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="puestos_propios",
                to="parametros.departamento",
                verbose_name="departamento específico",
            ),
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_filtrar_claustros",
            field=models.BooleanField(
                default=True,
                help_text="Sin uso: los claustros se definen al asociar el puesto.",
                verbose_name="permite limitar por claustros",
            ),
        ),
        migrations.AlterField(
            model_name="cargoelectivo",
            name="permite_filtrar_departamentos",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Departamental: se genera un puesto por cada departamento del claustro y solo pueden "
                    "postularse electores de ese departamento. General: se genera un único puesto por claustro "
                    "y puede postularse cualquier elector del claustro."
                ),
                verbose_name="puesto departamental",
            ),
        ),
        migrations.CreateModel(
            name="CupoPuestoClaustro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "cantidad_titulares",
                    models.PositiveSmallIntegerField(
                        default=1, validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "cantidad_suplentes",
                    models.PositiveSmallIntegerField(
                        default=1, validators=[django.core.validators.MinValueValidator(1)],
                    ),
                ),
                (
                    "claustro",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cupos_puestos_electivos",
                        to="parametros.claustro",
                    ),
                ),
                (
                    "puesto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cupos_claustro",
                        to="partidos.cargoelectivo",
                    ),
                ),
            ],
            options={
                "ordering": ("puesto__nombre", "claustro__nombre"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("puesto", "claustro"), name="cupo_unico_por_puesto_y_claustro",
                    ),
                ],
            },
        ),
        migrations.RunPython(crear_cupos_desde_puestos_existentes, migrations.RunPython.noop),
    ]
