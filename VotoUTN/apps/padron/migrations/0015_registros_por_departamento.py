from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("padron", "0014_registropadron_es_principal")]

    operations = [
        migrations.RemoveConstraint(model_name="registropadron", name="elector_unico_por_eleccion"),
        migrations.AddConstraint(
            model_name="registropadron",
            constraint=models.UniqueConstraint(
                fields=("elector", "eleccion", "eleccion_claustro_departamento"),
                name="padron_elector_alcance_unico",
            ),
        ),
        migrations.AddConstraint(
            model_name="registropadron",
            constraint=models.UniqueConstraint(
                fields=("elector", "eleccion"), condition=models.Q(es_principal=True),
                name="padron_principal_unico",
            ),
        ),
    ]
