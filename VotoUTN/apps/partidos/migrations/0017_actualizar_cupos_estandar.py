from django.db import migrations


CUPOS = (
    ("Consejo Directivo", "Consejero/a directivo/a", "Graduados", 5, 5),
    ("Consejo Directivo", "Consejero/a directivo/a", "No docentes", 1, 1),
    ("Consejo Superior", "Consejero/a Superior", "Docentes", 15, 15),
    ("Consejo Superior", "Consejero/a Superior", "Graduados", 5, 5),
    ("Consejo Superior", "Consejero/a Superior", "No docentes", 5, 5),
    ("Consejo DASUTeN", "Consejero/a DASUTeN", "Docentes", 2, 2),
    ("Consejo DASUTeN", "Consejero/a DASUTeN", "No docentes", 2, 2),
)


def actualizar_cupos(apps, schema_editor):
    alias = schema_editor.connection.alias
    cargo_modelo = apps.get_model("partidos", "CargoElectivo")
    cupo_modelo = apps.get_model("partidos", "CupoPuestoClaustro")
    puesto_modelo = apps.get_model("partidos", "PuestoEleccion")
    candidato_modelo = apps.get_model("partidos", "Candidato")
    claustro_modelo = apps.get_model("parametros", "Claustro")
    eleccion_claustro_modelo = apps.get_model("elecciones", "EleccionClaustro")

    for organo, nombre, nombre_claustro, titulares, suplentes in CUPOS:
        cargo = cargo_modelo.objects.using(alias).filter(organo__nombre=organo, nombre=nombre).first()
        if cargo is None:
            continue
        claustro = claustro_modelo.objects.using(alias).filter(nombre=nombre_claustro).first()
        if claustro is None:
            raise RuntimeError(f"No existe el claustro {nombre_claustro} para actualizar {nombre}.")
        if cargo.permite_filtrar_departamentos:
            raise RuntimeError(f"El puesto {nombre} no es general; revisalo antes de actualizar sus cupos.")
        puestos = puesto_modelo.objects.using(alias).filter(
            puesto=cargo, eleccion_claustro__claustro=claustro,
            eleccion_claustro__eleccion__estado="en_preparacion",
        )
        for puesto in puestos:
            for tipo, limite in (("titular", titulares), ("suplente", suplentes)):
                if candidato_modelo.objects.using(alias).filter(
                    lista__puesto_eleccion=puesto, tipo=tipo, orden__gt=limite,
                ).exists():
                    raise RuntimeError(
                        f"No se puede actualizar {nombre} para {nombre_claustro}: "
                        f"hay candidaturas {tipo} fuera del nuevo cupo."
                    )
        cargo.claustros_habilitados.add(claustro)
        cupo_modelo.objects.using(alias).update_or_create(
            puesto=cargo, claustro=claustro,
            defaults={"cantidad_titulares": titulares, "cantidad_suplentes": suplentes},
        )
        puestos.update(cantidad_titulares=titulares, cantidad_suplentes=suplentes)
        if cargo.activo and cargo.organo.activo:
            for eleccion_claustro in eleccion_claustro_modelo.objects.using(alias).filter(
                claustro=claustro, eleccion__estado="en_preparacion",
            ):
                puesto_modelo.objects.using(alias).get_or_create(
                    puesto=cargo, eleccion_claustro=eleccion_claustro,
                    eleccion_claustro_departamento=None,
                    defaults={"cantidad_titulares": titulares, "cantidad_suplentes": suplentes, "activo": True},
                )


class Migration(migrations.Migration):
    dependencies = [("partidos", "0016_renombrar_puestos_estandar")]

    operations = [migrations.RunPython(actualizar_cupos)]
