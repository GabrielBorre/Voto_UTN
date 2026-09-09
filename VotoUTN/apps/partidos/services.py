from django.db import transaction


@transaction.atomic
def guardar_con_validacion(formulario, **relaciones):
    instancia = formulario.save(commit=False)
    for nombre, valor in relaciones.items():
        setattr(instancia, nombre, valor)
    instancia.full_clean()
    instancia.save()
    return instancia
