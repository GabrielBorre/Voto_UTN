import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0001_initial"),
        ("parametros", "0002_catalogo_fechas_reutilizables"),
    ]

    operations = [
        migrations.AddField(
            model_name="plantillanotificacion",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("calendario", "Calendario administrativo"),
                    ("jornada", "Jornada electoral"),
                    ("transaccional", "Resultado de tramite"),
                    ("manual", "Envio manual"),
                ],
                default="manual",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="plantillanotificacion",
            name="codigo",
            field=models.SlugField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(model_name="plantillanotificacion", name="descripcion", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="plantillanotificacion",
            name="permite_envio_manual",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="ComunicacionFechaAdministrativa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.SlugField(max_length=80)),
                ("nombre", models.CharField(max_length=160)),
                ("referencia", models.CharField(choices=[("inicio", "Inicio"), ("fin", "Fin")], default="inicio", max_length=10)),
                ("desplazamiento_dias", models.SmallIntegerField(default=0)),
                ("hora_sugerida", models.TimeField(default="09:00")),
                ("orden", models.PositiveSmallIntegerField(default=1)),
                ("activa", models.BooleanField(default=True)),
                ("fecha_administrativa", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comunicaciones", to="parametros.fechaadministrativa")),
            ],
            options={"ordering": ("orden", "id")},
        ),
        migrations.CreateModel(
            name="VarianteComunicacionFechaAdministrativa",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criterio_adicional", models.CharField(blank=True, choices=[("", "Sin filtro adicional"), ("habilitado_cambio_sede", "Habilitado para cambio de sede"), ("sin_solicitud_presentada", "Sin solicitud presentada"), ("autoridad_vigente_sin_solicitud", "Autoridad vigente sin solicitud")], default="", max_length=50)),
                ("prioridad", models.PositiveSmallIntegerField(default=1)),
                ("activa", models.BooleanField(default=True)),
                ("comunicacion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variantes", to="notificaciones.comunicacionfechaadministrativa")),
                ("plantilla", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="variantes_calendario", to="notificaciones.plantillanotificacion")),
            ],
            options={"ordering": ("prioridad", "id")},
        ),
        migrations.AddConstraint(
            model_name="comunicacionfechaadministrativa",
            constraint=models.UniqueConstraint(fields=("fecha_administrativa", "codigo"), name="uniq_comunicacion_fecha_codigo"),
        ),
        migrations.AddConstraint(
            model_name="variantecomunicacionfechaadministrativa",
            constraint=models.UniqueConstraint(fields=("comunicacion", "prioridad"), name="uniq_variante_comunicacion_prioridad"),
        ),
    ]
