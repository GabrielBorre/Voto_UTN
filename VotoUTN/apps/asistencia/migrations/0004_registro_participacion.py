import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("asistencia", "0003_nomenclatura_en_espanol"),
        ("elecciones", "0005_identificador_qr_padron"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistroParticipacion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("registrada_en", models.DateTimeField(auto_now_add=True)),
                ("metodo", models.CharField(choices=[("qr", "QR"), ("manual", "Manual")], max_length=10)),
                ("mesa", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="participaciones", to="elecciones.mesa")),
                ("registrada_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("registro_padron", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="participaciones", to="elecciones.registropadron")),
            ],
        ),
        migrations.AddConstraint(
            model_name="registroparticipacion",
            constraint=models.UniqueConstraint(fields=("registro_padron",), name="participacion_unica_por_padron"),
        ),
    ]
