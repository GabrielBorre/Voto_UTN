from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0007_retirar_alcance_claustro_redundante"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE partidos_cargoelectivo "
                "ALTER COLUMN permite_claustro SET DEFAULT TRUE;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
