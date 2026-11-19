"""Carga todos los CSV de candidatos en sus listas y claustros del escenario.

Previsualiza por defecto. --aplicar confirma la carga completa en una transacción.
"""

import argparse
import csv
import io
import json
from pathlib import Path

from crear_listas_para_csv import BASE, CARPETAS, ErrorPreparacion, configurar_django, leer_csv, leer_definiciones, normalizar, preparar_listas


def clave_puesto(config):
    departamento = (config.eleccion_claustro_departamento.departamento.nombre
                    if config.eleccion_claustro_departamento_id and
                    config.eleccion_claustro_departamento.departamento_id else "")
    return normalizar(config.puesto.nombre), normalizar(departamento)


def preparar_puestos_escenario(eleccion, definiciones, usuario):
    """Configura únicamente los puestos y cupos requeridos por estos casos de prueba."""
    from apps.auditoria.services import registrar_evento
    from apps.elecciones.models import EleccionClaustro
    from apps.partidos.models import CargoElectivo, CupoPuestoClaustro, OrganoElectivo
    from apps.partidos.services import conflictos_de_cupo, sincronizar_puestos_claustro

    alcances = list(EleccionClaustro.objects.filter(eleccion=eleccion).select_related("claustro"))
    cambios, requisitos, usados = [], {}, {}
    for definicion in definiciones:
        for puesto in definicion["puestos"]:
            clave = definicion["claustro"], puesto["organo"], puesto["puesto"]
            cupos = (puesto["titulares"], puesto["suplentes"])
            if normalizar(puesto["puesto"]) == normalizar("Consejero/a DASUTeN"):
                cupos = (2, 2)
            valor = bool(puesto["departamento"]), cupos
            if clave in requisitos and requisitos[clave] != valor:
                raise ErrorPreparacion("Los archivos discrepan en el cupo o alcance de un puesto.")
            requisitos[clave] = valor
    for (claustro_nombre, organo_nombre, nombre), (departamental, cupos) in requisitos.items():
        candidatos = [ec for ec in alcances if ec.claustro.activo and normalizar(ec.claustro.nombre) == normalizar(claustro_nombre)]
        if len(candidatos) != 1:
            raise ErrorPreparacion(f"Falta un claustro activo y único {claustro_nombre} en la elección.")
        alcance = candidatos[0]
        organos = [o for o in OrganoElectivo.objects.all() if normalizar(o.nombre) == normalizar(organo_nombre)]
        if len(organos) > 1 or (organos and not organos[0].activo):
            raise ErrorPreparacion(f"Órgano ambiguo o inactivo: {organo_nombre}.")
        organo = organos[0] if organos else OrganoElectivo.objects.create(nombre=organo_nombre)
        cargos = [c for c in CargoElectivo.objects.filter(organo=organo) if normalizar(c.nombre) == normalizar(nombre)]
        activos = [c for c in cargos if c.activo]
        if len(activos) > 1 or (cargos and not activos):
            raise ErrorPreparacion(f"Puesto ambiguo o inactivo: {nombre}; revisalo en Parámetros.")
        cargo = activos[0] if activos else CargoElectivo.objects.create(
            organo=organo, nombre=nombre, permite_filtrar_departamentos=departamental,
        )
        if cargo.es_departamental != departamental:
            raise ErrorPreparacion(f"El alcance de {nombre} no coincide con el escenario.")
        conflictos = conflictos_de_cupo(cargo, alcance.claustro, *cupos)
        if conflictos:
            raise ErrorPreparacion(f"Los cupos de {nombre} dejarían candidaturas existentes fuera de rango: {conflictos}.")
        asociado = cargo.claustros_habilitados.filter(pk=alcance.claustro_id).exists()
        cargo.claustros_habilitados.add(alcance.claustro)
        cupo, creado = CupoPuestoClaustro.objects.get_or_create(
            puesto=cargo, claustro=alcance.claustro,
            defaults={"cantidad_titulares": cupos[0], "cantidad_suplentes": cupos[1]},
        )
        anteriores = None if creado else [cupo.cantidad_titulares, cupo.cantidad_suplentes]
        if creado or tuple(anteriores) != cupos:
            cupo.cantidad_titulares, cupo.cantidad_suplentes = cupos
            cupo.full_clean()
            cupo.save(update_fields=["cantidad_titulares", "cantidad_suplentes"])
        if creado or not asociado or tuple(anteriores) != cupos:
            cambios.append({"puesto_id": cargo.pk, "claustro_id": alcance.claustro_id,
                            "cupo_anterior": anteriores, "asociado_antes": asociado, "cupo_nuevo": list(cupos)})
        usados[alcance.pk] = alcance
    for alcance in usados.values():
        resumen = sincronizar_puestos_claustro(alcance)
        if resumen["eliminados"]:
            raise ErrorPreparacion("La sincronización intentó retirar puestos existentes; se revierte la operación.")
    if cambios:
        registrar_evento(accion="preparar_puestos_csv_escenario", entidad=eleccion._meta.label,
                         entidad_id=eleccion.pk, eleccion=eleccion, usuario=usuario,
                         datos_nuevos={"cambios": cambios, "origen": "CSV segmento_1_500"})
    return len(cambios)


def cargar_candidatos(eleccion_id, definiciones, *, usuario, base=BASE, aplicar=False,
                      ajustar_asociaciones=False, reiniciar_listas=False, preparar_puestos=False):
    from django.core.exceptions import ValidationError
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import transaction
    from apps.auditoria.services import registrar_evento
    from apps.elecciones.models import Eleccion
    from apps.partidos.models import Candidato, ListaCandidatos, ParticipacionPartido
    from apps.partidos.services import (
        ENCABEZADOS_CANDIDATOS_MULTIPUESTO, buscar_elector_candidato,
        confirmar_candidatos_multipuesto, previsualizar_candidatos_multipuesto,
        puestos_habilitados_multipuesto,
    )
    from apps.usuarios.permisos import puede_administrar_elecciones

    if usuario is None or not usuario.is_active or not puede_administrar_elecciones(usuario):
        raise ErrorPreparacion("Indicá un usuario activo con permisos de administrador de junta.")
    with transaction.atomic():
        eleccion = Eleccion.objects.select_for_update().get(pk=eleccion_id)
        if eleccion.estado != Eleccion.Estado.EN_PREPARACION:
            raise ErrorPreparacion("La elección debe estar En preparación para cargar candidatos.")
        reinicio = {"candidaturas_eliminadas": 0, "asociaciones_eliminadas": 0, "listas_eliminadas": 0}
        if reiniciar_listas:
            if {normalizar(d["claustro"]).replace(" ", "_") for d in definiciones} != set(CARPETAS):
                raise ErrorPreparacion("El reinicio requiere los cuatro claustros; no se puede combinar con filtros.")
            candidaturas = Candidato.objects.filter(lista__participacion__eleccion=eleccion)
            asociaciones = ListaCandidatos.objects.filter(participacion__eleccion=eleccion)
            listas = ParticipacionPartido.objects.filter(eleccion=eleccion)
            copia = {
                "candidaturas": list(candidaturas.select_for_update(of=("self",)).values()),
                "asociaciones": list(asociaciones.select_for_update(of=("self",)).values()),
                "listas": list(listas.select_for_update(of=("self",)).values()),
            }
            reinicio = {"candidaturas_eliminadas": len(copia["candidaturas"]),
                        "asociaciones_eliminadas": len(copia["asociaciones"]),
                        "listas_eliminadas": len(copia["listas"])}
            registrar_evento(accion="reiniciar_listas_candidatos_escenario", entidad=eleccion._meta.label,
                             entidad_id=eleccion.pk, eleccion=eleccion, usuario=usuario,
                             datos_anteriores=copia, datos_nuevos=reinicio)
            candidaturas.delete()
            asociaciones.delete()
            listas.delete()
        parametros_actualizados = preparar_puestos_escenario(eleccion, definiciones, usuario) if preparar_puestos else 0
        preparacion = preparar_listas(eleccion_id, definiciones, aplicar=True, usuario=usuario)
        resultado = {"eleccion_id": eleccion_id, "aplicado": aplicar, "candidatos_nuevos": 0,
                     "candidatos_identicos_omitidos": 0, "asociaciones_vacias_retiradas": 0,
                     "listas": [], "listas_nuevas": preparacion["listas_nuevas"], "reinicio": reinicio,
                     "parametros_actualizados": parametros_actualizados}
        for definicion, plan in zip(definiciones, preparacion["listas"], strict=True):
            participacion = ParticipacionPartido.objects.select_for_update().get(pk=plan["presentacion_id"])
            configs = list(puestos_habilitados_multipuesto(participacion))
            esperados = {(normalizar(p["puesto"]), normalizar(p["departamento"])) for p in definicion["puestos"]}
            mapa = {}
            for config in configs:
                clave = clave_puesto(config)
                if clave in esperados:
                    if clave in mapa:
                        raise ErrorPreparacion(f"{definicion['codigo_presentacion']}: puesto ambiguo.")
                    mapa[clave] = config
            if set(mapa) != esperados:
                raise ErrorPreparacion(f"{definicion['codigo_presentacion']}: falta asociar un puesto del archivo.")
            if ajustar_asociaciones:
                ids = {config.pk for config in mapa.values()}
                for asociacion in participacion.listas.select_for_update().exclude(puesto_eleccion_id__in=ids):
                    if asociacion.candidatos.exists():
                        raise ErrorPreparacion(f"{definicion['codigo_presentacion']}: un puesto ajeno al CSV ya tiene candidatos; no se elimina.")
                    registrar_evento(
                        accion="retirar_asociacion_vacia_escenario", entidad=asociacion._meta.label,
                        entidad_id=asociacion.pk, eleccion=eleccion, usuario=usuario,
                        datos_anteriores={"participacion": participacion.pk, "puesto_eleccion": asociacion.puesto_eleccion_id},
                    )
                    asociacion.delete()
                    resultado["asociaciones_vacias_retiradas"] += 1
            ruta = (Path(base) / definicion["csv_candidatos"]).resolve()
            if not ruta.is_relative_to(Path(base).resolve()):
                raise ErrorPreparacion("El CSV está fuera de la carpeta del escenario.")
            filas = leer_csv(ruta)
            pendientes, omitidos, espacios = [], 0, set()
            for fila in filas:
                clave = normalizar(fila["puesto"]), normalizar(fila["departamento"])
                config = mapa.get(clave)
                tipo = normalizar(fila["tipo_candidatura"])
                try:
                    orden = int(fila["orden"])
                except (ValueError, TypeError) as error:
                    raise ErrorPreparacion(f"{ruta.name}: orden inválido.") from error
                if config is None or tipo not in ("titular", "suplente") or orden < 1:
                    raise ErrorPreparacion(f"{ruta.name}: puesto, tipo u orden inválido.")
                espacio = config.pk, tipo, orden
                if espacio in espacios:
                    raise ErrorPreparacion(f"{ruta.name}: puesto, tipo y orden repetidos en el CSV.")
                espacios.add(espacio)
                existente = Candidato.objects.select_for_update(of=("self",)).select_related("elector").filter(
                    lista__participacion=participacion, lista__puesto_eleccion=config, tipo=tipo, orden=orden,
                ).first()
                if existente:
                    elector = buscar_elector_candidato(eleccion=eleccion, puesto=config,
                                                       tipo_documento=fila["tipo_documento"], documento=fila["documento"])
                    if not existente.activo or existente.elector_id != elector.pk:
                        raise ErrorPreparacion(f"{ruta.name}: el puesto {tipo} {orden} está ocupado por otra candidatura o está inactivo.")
                    existente.full_clean()
                    omitidos += 1
                else:
                    pendientes.append(fila)
            advertencias = []
            if pendientes:
                contenido = io.StringIO(newline="")
                escritor = csv.DictWriter(contenido, fieldnames=ENCABEZADOS_CANDIDATOS_MULTIPUESTO,
                                         delimiter=";", extrasaction="ignore")
                escritor.writeheader()
                escritor.writerows(pendientes)
                archivo = SimpleUploadedFile(ruta.name, contenido.getvalue().encode("utf-8-sig"))
                importacion = previsualizar_candidatos_multipuesto(participacion=participacion, archivo=archivo, usuario=usuario)
                if importacion.errores:
                    raise ErrorPreparacion(f"{definicion['codigo_presentacion']} / {ruta.name}:\n- " + "\n- ".join(importacion.errores))
                advertencias = importacion.advertencias
                nuevos = confirmar_candidatos_multipuesto(importacion, participacion)
                registrar_evento(
                    accion="importar_candidatos_csv_escenario", entidad=participacion._meta.label,
                    entidad_id=participacion.pk, eleccion=eleccion, usuario=usuario,
                    datos_nuevos={"archivo": str(ruta.relative_to(Path(base).resolve())),
                                  "importacion": importacion.pk, "candidatos": nuevos,
                                  "advertencias": advertencias},
                )
            else:
                nuevos = 0
            resultado["candidatos_nuevos"] += nuevos
            resultado["candidatos_identicos_omitidos"] += omitidos
            resultado["listas"].append({"codigo": definicion["codigo_presentacion"],
                                       "claustro": definicion["claustro"], "nombre": definicion["nombre_lista"],
                                       "csv": definicion["csv_candidatos"], "nuevos": nuevos,
                                       "identicos_omitidos": omitidos, "advertencias": advertencias})
        if not aplicar:
            transaction.set_rollback(True)
        return resultado


def main():
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--eleccion", type=int, required=True)
    argumentos.add_argument("--usuario", required=True, help="Usuario local administrador de junta responsable.")
    argumentos.add_argument("--claustro", action="append", choices=tuple(CARPETAS))
    argumentos.add_argument("--aplicar", action="store_true")
    argumentos.add_argument("--preparar-puestos", action="store_true",
                           help="Configura los puestos y cupos de estos casos antes de cargar; requiere claustros, departamentos y padrones ya existentes.")
    argumentos.add_argument("--reiniciar-listas", action="store_true",
                           help="Vacía candidaturas, listas y sus asociaciones de esta elección antes de cargar los cuatro claustros; conserva copia en auditoría.")
    argumentos.add_argument("--ajustar-asociaciones", action="store_true",
                           help="Retira asociaciones vacías de estas listas que no figuran en sus CSV; nunca elimina candidatos.")
    argumentos.add_argument("--proyecto", type=Path, default=BASE.parents[1] / "VotoUTN")
    opciones = argumentos.parse_args()
    if opciones.reiniciar_listas and opciones.claustro:
        argumentos.error("--reiniciar-listas no se puede combinar con --claustro")
    try:
        definiciones = leer_definiciones(claustros=opciones.claustro)
        configurar_django(opciones.proyecto)
        from django.contrib.auth import get_user_model
        from django.core.exceptions import ObjectDoesNotExist, ValidationError
        from django.db import DatabaseError
        usuario = get_user_model().objects.filter(username=opciones.usuario, is_active=True).first()
        resultado = cargar_candidatos(opciones.eleccion, definiciones, usuario=usuario,
                                      aplicar=opciones.aplicar, ajustar_asociaciones=opciones.ajustar_asociaciones,
                                      reiniciar_listas=opciones.reiniciar_listas, preparar_puestos=opciones.preparar_puestos)
    except (ErrorPreparacion, OSError, KeyError) as error:
        argumentos.exit(1, f"No se guardó ningún cambio: {error}\n")
    except ImportError:
        argumentos.exit(1, "Ejecutá el script con las dependencias del proyecto o dentro de su contenedor.\n")
    except (ObjectDoesNotExist, ValidationError) as error:
        argumentos.exit(1, f"No se guardó ningún cambio: {error}\n")
    except DatabaseError:
        argumentos.exit(1, "Error de base de datos: se revirtió la operación completa.\n")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    print("Carga completa confirmada." if opciones.aplicar else "Previsualización completada: no se guardaron cambios.")


if __name__ == "__main__":
    main()
