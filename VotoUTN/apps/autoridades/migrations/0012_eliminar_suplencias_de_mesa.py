from django.db import migrations, models


def eliminar_suplencias(apps, schema_editor):
    Asignacion = apps.get_model("autoridades", "AsignacionAutoridad")
    Candidatura = apps.get_model("autoridades", "CandidaturaAutoridad")
    ConfiguracionTurno = apps.get_model("elecciones", "EleccionClaustroTurno")
    Perfil = apps.get_model("usuarios", "PerfilUsuario")
    Rol = apps.get_model("usuarios", "AsignacionRol")

    suplencias = list(Asignacion.objects.filter(tipo="suplente").values_list(
        "registro_padron__elector_id", "registro_padron__eleccion_id", "mesa_id",
    ))
    for elector_id, eleccion_id, mesa_id in suplencias:
        usuarios = Perfil.objects.filter(elector_id=elector_id).values_list("usuario_id", flat=True)
        Rol.objects.filter(usuario_id__in=usuarios, rol="autoridad_mesa", eleccion_id=eleccion_id, mesa_id=mesa_id).delete()
    Asignacion.objects.filter(tipo="suplente").delete()
    Candidatura.objects.filter(tipo_manual="suplente").update(
        mesa_manual=None, turno_manual=None, tipo_manual="", orden_manual=None,
        mesa_traslado=None, turno_traslado=None,
    )
    ConfiguracionTurno.objects.filter(suplentes_por_mesa__gt=0).update(suplentes_por_mesa=0)


class Migration(migrations.Migration):
    dependencies = [
        ("autoridades", "0011_asignacionautoridad_mesa_votacion_original"),
        ("usuarios", "0003_perfilusuario_dni"),
    ]

    operations = [
        migrations.RunPython(eliminar_suplencias),
        migrations.AddConstraint(
            model_name="asignacionautoridad",
            constraint=models.CheckConstraint(condition=models.Q(tipo="titular"), name="autoridad_solo_titular"),
        ),
    ]
