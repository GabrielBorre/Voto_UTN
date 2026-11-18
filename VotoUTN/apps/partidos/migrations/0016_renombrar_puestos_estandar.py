from django.db import migrations


def renombrar_puestos(apps, schema_editor):
    cargo = apps.get_model("partidos", "CargoElectivo")
    alias = schema_editor.connection.alias
    nombres = (
        ("Consejo Superior", ("Consejo Superior", "Consejero/a superior", "Consejero/a Superior"), "Consejero/a Superior"),
        (
            "Consejo Departamental",
            ("Ciencias Basicas", "Consejero/a departamental de Ciencias Básicas", "Consejero/a Ciencias Básicas"),
            "Consejero/a Ciencias Básicas",
        ),
    )
    for organo, anteriores, nuevo in nombres:
        puestos = list(cargo.objects.using(alias).filter(organo__nombre=organo, nombre__in=anteriores))
        if len(puestos) > 1:
            raise RuntimeError(f"Hay varios puestos equivalentes a {nuevo}; revisalos antes de migrar.")
        if puestos and puestos[0].nombre != nuevo:
            cargo.objects.using(alias).filter(pk=puestos[0].pk).update(nombre=nuevo)


class Migration(migrations.Migration):
    dependencies = [("partidos", "0015_cupos_por_claustro_y_alcance_del_puesto")]

    operations = [migrations.RunPython(renombrar_puestos)]
