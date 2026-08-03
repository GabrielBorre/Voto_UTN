from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("asistencia", "0002_alter_asistencia_voter_code"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="asistencia",
            old_name="voter_code",
            new_name="codigo_elector",
        ),
        migrations.RenameField(
            model_name="asistencia",
            old_name="scanned_by",
            new_name="registrada_por",
        ),
        migrations.RenameField(
            model_name="asistencia",
            old_name="scanned_at",
            new_name="registrada_en",
        ),
        migrations.AlterField(
            model_name="asistencia",
            name="eleccion",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="asistencias",
                to="elecciones.eleccion",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="asistencia",
            name="unique_attendance_per_election",
        ),
        migrations.AddConstraint(
            model_name="asistencia",
            constraint=models.UniqueConstraint(
                fields=("eleccion", "codigo_elector"),
                name="asistencia_unica_por_eleccion",
            ),
        ),
        migrations.RemoveIndex(
            model_name="asistencia",
            name="asistencia__eleccio_357671_idx",
        ),
        migrations.AddIndex(
            model_name="asistencia",
            index=models.Index(
                fields=["eleccion", "codigo_elector"],
                name="asistencia_eleccion_codigo_idx",
            ),
        ),
    ]
