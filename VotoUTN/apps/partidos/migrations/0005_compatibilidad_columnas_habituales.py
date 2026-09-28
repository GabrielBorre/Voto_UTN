from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("partidos", "0004_retirar_campos_habituales_del_estado"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE partidos_partido "
                "ALTER COLUMN numero_lista_habitual SET DEFAULT '';"
                "ALTER TABLE partidos_partido "
                "ALTER COLUMN apoderado_habitual SET DEFAULT '';"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
