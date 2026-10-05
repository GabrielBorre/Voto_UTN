from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elecciones", "0020_delete_elector_delete_envionotificacion_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "elecciones_eleccion" '
                        'ALTER COLUMN "fecha_inicio" TYPE date '
                        'USING (("fecha_inicio" AT TIME ZONE '
                        "'America/Argentina/Buenos_Aires')::date)"
                    ),
                    reverse_sql=(
                        'ALTER TABLE "elecciones_eleccion" '
                        'ALTER COLUMN "fecha_inicio" TYPE timestamp with time zone '
                        'USING (("fecha_inicio"::timestamp) AT TIME ZONE '
                        "'America/Argentina/Buenos_Aires')"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "elecciones_eleccion" '
                        'ALTER COLUMN "fecha_fin" TYPE date '
                        'USING (("fecha_fin" AT TIME ZONE '
                        "'America/Argentina/Buenos_Aires')::date)"
                    ),
                    reverse_sql=(
                        'ALTER TABLE "elecciones_eleccion" '
                        'ALTER COLUMN "fecha_fin" TYPE timestamp with time zone '
                        'USING (("fecha_fin"::timestamp) AT TIME ZONE '
                        "'America/Argentina/Buenos_Aires')"
                    ),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="eleccion",
                    name="fecha_inicio",
                    field=models.DateField(verbose_name="fecha de inicio del proceso"),
                ),
                migrations.AlterField(
                    model_name="eleccion",
                    name="fecha_fin",
                    field=models.DateField(verbose_name="fecha de fin del proceso"),
                ),
            ],
        ),
    ]
