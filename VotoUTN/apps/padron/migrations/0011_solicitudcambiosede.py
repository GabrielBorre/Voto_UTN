import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("padron", "0010_merge_20261011_2053"),
        ("parametros", "0004_claustro_organizacion_departamentos"),
        ("elecciones", "0026_eleccion_fecha_cierre_solicitudes_cambio_sede"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitudCambioSede",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado", models.CharField(choices=[("pendiente", "Pendiente"), ("aprobada", "Aprobada"), ("rechazada", "Rechazada")], default="pendiente", max_length=16)),
                ("observacion", models.TextField(blank=True)),
                ("observacion_resolucion", models.TextField(blank=True)),
                ("creada_en", models.DateTimeField(auto_now_add=True)),
                ("resuelta_en", models.DateTimeField(blank=True, null=True)),
                ("registro_padron", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_cambio_sede", to="padron.registropadron")),
                ("resuelta_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_cambio_sede_resueltas", to=settings.AUTH_USER_MODEL)),
                ("sede_destino", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_cambio_destino", to="parametros.sede")),
                ("sede_origen", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_cambio_origen", to="parametros.sede")),
            ],
            options={
                "db_table": "elecciones_solicitudcambiosede",
                "ordering": ("-creada_en",),
            },
        ),
        migrations.AddConstraint(
            model_name="solicitudcambiosede",
            constraint=models.UniqueConstraint(condition=models.Q(("estado", "pendiente")), fields=("registro_padron",), name="solicitud_cambio_sede_pendiente_unica"),
        ),
    ]
