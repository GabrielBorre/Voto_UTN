from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(name="Election", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("name", models.CharField(max_length=180, verbose_name="nombre")),
        ("starts_at", models.DateTimeField(verbose_name="inicio")), ("ends_at", models.DateTimeField(verbose_name="fin")),
        ("is_active", models.BooleanField(default=True, verbose_name="habilitada")),
    ], options={"ordering": ["-starts_at"]})]
