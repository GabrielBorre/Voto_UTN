from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("parametros", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="fechaadministrativa",
            name="alcance_todos_claustros",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="fechaadministrativa",
            name="codigo",
            field=models.SlugField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="fechaadministrativa",
            name="criterio_destinatarios",
            field=models.CharField(
                choices=[
                    ("todos_en_alcance", "Todos los destinatarios del alcance"),
                    ("electores_activos_padron", "Electores activos en el padron"),
                    ("electores_ausentes_confirmados", "Electores con ausencia confirmada"),
                    ("autoridades_asignadas", "Autoridades asignadas"),
                    ("autoridades_ausentes_confirmadas", "Autoridades con ausencia confirmada"),
                ],
                default="todos_en_alcance",
                max_length=50,
            ),
        ),
        migrations.AddField(model_name="fechaadministrativa", name="descripcion", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="fechaadministrativa",
            name="duracion_sugerida_dias",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fechaadministrativa",
            name="evento_disparador_sugerido",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Sin evento automatico"),
                    ("publicacion_padron", "Publicacion de padron"),
                    ("ausencia_electoral", "Ausencia electoral confirmada"),
                    ("ausencia_autoridad", "Ausencia de autoridad confirmada"),
                    ("designacion_autoridad", "Designacion de autoridad"),
                    ("capacitacion_autoridad", "Capacitacion de autoridades"),
                ],
                default="",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="fechaadministrativa",
            name="modalidad_sugerida",
            field=models.CharField(
                choices=[
                    ("fecha_unica", "Fecha unica"),
                    ("rango", "Rango de fechas"),
                    ("duracion", "Duracion desde la fecha de inicio"),
                ],
                default="fecha_unica",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="fechaadministrativa",
            name="claustros",
            field=models.ManyToManyField(
                blank=True,
                db_table="elecciones_fechaadministrativa_claustros",
                related_name="fechas_administrativas",
                to="parametros.claustro",
            ),
        ),
    ]
