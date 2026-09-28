from django.db import migrations
from django.utils.text import slugify


def codigo_unico(modelo, base, limite):
    base = (slugify(base) or "registro")[:limite]
    candidato = base
    numero = 2
    while modelo.objects.filter(codigo=candidato).exists():
        sufijo = f"-{numero}"
        candidato = f"{base[: limite - len(sufijo)]}{sufijo}"
        numero += 1
    return candidato


def nombre_unico(modelo, base, limite):
    base = base[:limite]
    candidato = base
    numero = 2
    while modelo.objects.filter(nombre=candidato).exists():
        sufijo = f" ({numero})"
        candidato = f"{base[: limite - len(sufijo)]}{sufijo}"
        numero += 1
    return candidato


def preservar_mensajes(apps, schema_editor):
    Fecha = apps.get_model("parametros", "FechaAdministrativa")
    Plantilla = apps.get_model("notificaciones", "PlantillaNotificacion")
    Comunicacion = apps.get_model("notificaciones", "ComunicacionFechaAdministrativa")
    Variante = apps.get_model("notificaciones", "VarianteComunicacionFechaAdministrativa")

    for plantilla in Plantilla.objects.filter(codigo__isnull=True):
        plantilla.codigo = codigo_unico(Plantilla, plantilla.nombre, 100)
        plantilla.save(update_fields=("codigo",))

    for fecha in Fecha.objects.all():
        fecha.codigo = codigo_unico(Fecha, fecha.nombre, 80)
        fecha.save(update_fields=("codigo",))
        if not fecha.asunto_notificacion and not fecha.mensaje_notificacion:
            continue
        plantilla = Plantilla.objects.create(
            codigo=codigo_unico(Plantilla, f"fecha-{fecha.codigo}", 100),
            nombre=nombre_unico(Plantilla, f"Mensaje de {fecha.nombre}", 160),
            categoria="calendario",
            asunto=fecha.asunto_notificacion,
            contenido=fecha.mensaje_notificacion,
            roles_destinatarios=fecha.roles_destinatarios,
            permite_envio_manual=False,
            activa=fecha.activa,
        )
        plantilla.claustros.set(fecha.claustros.all())
        comunicacion = Comunicacion.objects.create(
            fecha_administrativa=fecha,
            codigo="principal",
            nombre="Comunicacion principal",
        )
        Variante.objects.create(comunicacion=comunicacion, plantilla=plantilla)


class Migration(migrations.Migration):
    dependencies = [
        ("notificaciones", "0002_catalogo_plantillas_y_comunicaciones"),
        ("parametros", "0002_catalogo_fechas_reutilizables"),
    ]

    operations = [migrations.RunPython(preservar_mensajes, migrations.RunPython.noop)]
