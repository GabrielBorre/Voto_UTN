from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("elections", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Voter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("legajo", models.CharField(max_length=20, unique=True, verbose_name="legajo")),
                ("name", models.CharField(max_length=180, verbose_name="nombre")),
                ("dni", models.CharField(max_length=12, unique=True, verbose_name="DNI")),
            ],
            options={"ordering": ["legajo"], "verbose_name": "elector", "verbose_name_plural": "electores"},
        ),
    ]
