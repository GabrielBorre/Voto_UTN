"""Prepara las listas de los cuatro claustros para cargar sus CSV de candidatos.

Usar --eleccion ID para previsualizar; agregar --aplicar para guardar.
No carga candidatos ni cambia puestos, cupos, claustros o padrones.
"""

import argparse
import csv
import json
import os
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


BASE = Path(__file__).resolve().parent
CARPETAS = {
    "estudiantes": "listas_estudiantes_sin_autoridades",
    "graduados": "listas_graduados_sin_autoridades",
    "docentes": "listas_docentes_sin_autoridades",
    "no_docentes": "listas_no_docentes_sin_autoridades",
}
METADATOS = ("codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email", "claustro")


class ErrorPreparacion(ValueError):
    """La preparación no puede aplicarse sin resolver los problemas informados."""


def normalizar(valor):
    texto = unicodedata.normalize("NFKD", valor.strip())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).casefold().split())


def leer_csv(ruta):
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def leer_definiciones(base=BASE, claustros=None):
    """Obtiene metadatos y puestos de los archivos existentes, sin conectar a la base."""
    seleccion = list(CARPETAS) if claustros is None else list(dict.fromkeys(claustros))
    if not seleccion or set(seleccion) - CARPETAS.keys():
        raise ErrorPreparacion("Seleccioná uno o varios claustros válidos.")
    definiciones, codigos = [], set()
    for clave in seleccion:
        carpeta = Path(base) / CARPETAS[clave]
        metadatos = leer_csv(carpeta / "listas_y_apoderados.csv")
        completas = carpeta / "importacion_completa"
        if not completas.is_dir():
            completas = carpeta  # Estudiantes tiene el CSV completo en la raíz.
        archivos = {}
        for ruta in sorted(completas.glob("lista_*.csv")):
            filas = leer_csv(ruta)
            if not filas or any(not set(METADATOS).issubset(fila) for fila in filas):
                raise ErrorPreparacion(f"{ruta.name}: falta información de presentación.")
            codigo = filas[0]["codigo_presentacion"]
            if codigo in archivos:
                raise ErrorPreparacion(f"Código repetido en archivos: {codigo}.")
            archivos[codigo] = ruta, filas
        for datos in metadatos:
            if any(not datos.get(campo, "").strip() for campo in METADATOS):
                raise ErrorPreparacion(f"{carpeta.name}: metadatos incompletos.")
            codigo = datos["codigo_presentacion"]
            if codigo in codigos or codigo not in archivos:
                raise ErrorPreparacion(f"{codigo}: código repetido o sin CSV de candidatos.")
            codigos.add(codigo)
            ruta, filas = archivos.pop(codigo)
            ordenes = defaultdict(lambda: {"titular": set(), "suplente": set()})
            for fila in filas:
                if any(fila[campo] != datos[campo] for campo in METADATOS):
                    raise ErrorPreparacion(f"{codigo}: los metadatos del CSV no coinciden.")
                puesto = fila["organo"], fila["puesto"], fila["departamento"]
                tipo = fila["tipo_candidatura"]
                try:
                    orden = int(fila["orden"])
                except (ValueError, TypeError) as error:
                    raise ErrorPreparacion(f"{codigo}: orden inválido.") from error
                if not puesto[0] or not puesto[1] or tipo not in ("titular", "suplente") or orden < 1:
                    raise ErrorPreparacion(f"{codigo}: puesto, tipo u orden inválido.")
                if orden in ordenes[puesto][tipo]:
                    raise ErrorPreparacion(f"{codigo}: un puesto repite tipo y orden.")
                ordenes[puesto][tipo].add(orden)
            requisitos = []
            for (organo, puesto, departamento), tipos in ordenes.items():
                for valores in tipos.values():
                    if not valores or valores != set(range(1, len(valores) + 1)):
                        raise ErrorPreparacion(f"{codigo}: candidaturas incompletas o sin orden consecutivo.")
                requisitos.append({"organo": organo, "puesto": puesto, "departamento": departamento,
                                   "titulares": len(tipos["titular"]), "suplentes": len(tipos["suplente"])})
            multipuesto = carpeta / "multipuesto" / ruta.name
            if not multipuesto.is_file():
                multipuesto = carpeta / ruta.name
            if not multipuesto.is_file():
                raise ErrorPreparacion(f"{codigo}: falta el CSV para cargar dentro de la lista.")
            definiciones.append({**{k: datos[k] for k in METADATOS}, "puestos": requisitos,
                                 "csv_candidatos": str(multipuesto.relative_to(base))})
        if archivos:
            raise ErrorPreparacion(f"{carpeta.name}: hay CSV sin metadatos de presentación.")
    return definiciones


def preparar_listas(eleccion_id, definiciones, *, aplicar=False, usuario=None):
    """Valida todo antes de escribir; conserva datos existentes y revierte ante errores."""
    from django.db import transaction
    from apps.auditoria.services import registrar_evento
    from apps.elecciones.models import Eleccion, EleccionClaustro
    from apps.partidos.models import ListaCandidatos, ParticipacionPartido, PuestoEleccion

    if not definiciones:
        raise ErrorPreparacion("No hay listas para preparar.")
    with transaction.atomic():
        try:
            eleccion = Eleccion.objects.select_for_update().get(pk=eleccion_id)
        except Eleccion.DoesNotExist as error:
            raise ErrorPreparacion(f"No existe la elección {eleccion_id}.") from error
        if eleccion.estado != Eleccion.Estado.EN_PREPARACION:
            raise ErrorPreparacion("La elección debe estar En preparación para crear listas.")
        alcances = list(EleccionClaustro.objects.filter(eleccion=eleccion).select_related("claustro"))
        existentes = list(ParticipacionPartido.objects.select_for_update(of=("self",)).filter(eleccion=eleccion))
        configuraciones = list(PuestoEleccion.objects.select_for_update(of=("self",)).filter(
            eleccion_claustro__eleccion=eleccion, activo=True, puesto__activo=True,
            puesto__organo__activo=True,
        ).select_related("puesto__organo", "eleccion_claustro", "eleccion_claustro_departamento__departamento"))
        planes, errores, asignadas = [], [], set()
        for definicion in definiciones:
            codigo = definicion["codigo_presentacion"]
            coincidencias = [a for a in alcances if a.claustro.activo and
                             normalizar(a.claustro.nombre) == normalizar(definicion["claustro"])]
            if len(coincidencias) != 1:
                errores.append(f"{codigo}: debe haber un único claustro activo {definicion['claustro']} en la elección.")
                continue
            alcance = coincidencias[0]
            por_codigo = [p for p in existentes if p.codigo_presentacion == codigo]
            por_identidad = [p for p in existentes if p.eleccion_claustro_id == alcance.pk and
                            p.numero_lista == definicion["numero_lista"] and
                            normalizar(p.nombre_lista) == normalizar(definicion["nombre_lista"])]
            candidatos = por_codigo or por_identidad
            if len(candidatos) > 1 or (por_codigo and any(p.pk != por_codigo[0].pk for p in por_identidad)):
                errores.append(f"{codigo}: hay presentaciones duplicadas o ambiguas.")
                continue
            presentacion = candidatos[0] if candidatos else None
            if presentacion and (not presentacion.activa or presentacion.eleccion_claustro_id != alcance.pk or
                                 presentacion.numero_lista != definicion["numero_lista"] or
                                 normalizar(presentacion.nombre_lista) != normalizar(definicion["nombre_lista"])):
                errores.append(f"{codigo}: la presentación existente está inactiva o tiene otra identidad.")
                continue
            if presentacion and presentacion.pk in asignadas:
                errores.append(f"{codigo}: dos definiciones apuntan a la misma presentación.")
                continue
            if presentacion:
                asignadas.add(presentacion.pk)
            puestos = []
            for requisito in definicion["puestos"]:
                encontrados = []
                for config in configuraciones:
                    departamento = (config.eleccion_claustro_departamento.departamento.nombre
                                    if config.eleccion_claustro_departamento_id and
                                    config.eleccion_claustro_departamento.departamento_id else "")
                    if config.eleccion_claustro_id == alcance.pk and (
                        normalizar(config.puesto.organo.nombre), normalizar(config.puesto.nombre), normalizar(departamento)
                    ) == tuple(normalizar(requisito[k]) for k in ("organo", "puesto", "departamento")):
                        encontrados.append(config)
                etiqueta = f"{codigo}: {requisito['puesto']} / {requisito['departamento'] or 'general'}"
                if len(encontrados) != 1:
                    errores.append(f"{etiqueta}: falta un puesto único y activo. Revisá Parámetros y sincronizá la elección.")
                    continue
                config = encontrados[0]
                if not config.puesto.claustros_habilitados.filter(pk=alcance.claustro_id).exists():
                    errores.append(f"{etiqueta}: el puesto no está habilitado para este claustro.")
                    continue
                for tipo, limite in (("titulares", config.cantidad_titulares), ("suplentes", config.cantidad_suplentes)):
                    cantidad = requisito[tipo]
                    if not (1 <= cantidad <= limite) or cantidad < (limite + 1) // 2:
                        errores.append(f"{etiqueta}: CSV con {cantidad} {tipo}, cupo {limite}; debe cubrir entre 50 % y 100 %. "
                                       "Para Directivo de Docentes, estos casos requieren configurar el cupo en 2+2.")
                asociacion = (ListaCandidatos.objects.select_for_update().filter(
                    participacion=presentacion, puesto_eleccion=config,
                ).first() if presentacion else None)
                if asociacion and (not asociacion.activa or asociacion.eleccion_claustro_id != alcance.pk or
                                   asociacion.eleccion_claustro_departamento_id != config.eleccion_claustro_departamento_id):
                    errores.append(f"{etiqueta}: la asociación existente está inactiva o tiene otro alcance.")
                puestos.append((config, asociacion))
            planes.append((definicion, alcance, presentacion, puestos))
        if errores:
            raise ErrorPreparacion("No se guardó ningún cambio:\n- " + "\n- ".join(errores))

        resultado = {"eleccion_id": eleccion.pk, "eleccion": eleccion.nombre, "aplicado": aplicar,
                     "listas_nuevas": 0, "asociaciones_nuevas": 0, "listas": []}
        for definicion, alcance, presentacion, puestos in planes:
            nueva = presentacion is None
            resultado["listas_nuevas"] += int(nueva)
            datos_auditoria = {"origen": "crear_listas_para_csv.py", "codigo_csv": definicion["codigo_presentacion"]}
            if aplicar and nueva:
                presentacion = ParticipacionPartido(
                    eleccion=eleccion, eleccion_claustro=alcance,
                    **{k: definicion[k] for k in METADATOS if k != "claustro"},
                )
                presentacion.full_clean()
                presentacion.save()
                registrar_evento(accion="crear_presentacion_desde_escenario", entidad=presentacion._meta.label,
                                 entidad_id=presentacion.pk, eleccion=eleccion, usuario=usuario,
                                 datos_nuevos={**datos_auditoria, "numero_lista": presentacion.numero_lista,
                                               "nombre_lista": presentacion.nombre_lista})
            faltantes = sum(asociacion is None for _, asociacion in puestos)
            resultado["asociaciones_nuevas"] += faltantes
            for config, asociacion in puestos:
                if aplicar and asociacion is None:
                    asociacion = ListaCandidatos(
                        participacion=presentacion, eleccion_claustro=alcance,
                        eleccion_claustro_departamento=config.eleccion_claustro_departamento,
                        puesto_eleccion=config, nombre=str(config.puesto),
                    )
                    asociacion.full_clean()
                    asociacion.save()
                    registrar_evento(accion="vincular_puesto_a_presentacion", entidad=asociacion._meta.label,
                                     entidad_id=asociacion.pk, eleccion=eleccion, usuario=usuario,
                                     datos_nuevos={**datos_auditoria, "participacion": presentacion.pk,
                                                   "puesto_eleccion": config.pk})
            resultado["listas"].append({
                "codigo_csv": definicion["codigo_presentacion"], "claustro": definicion["claustro"],
                "numero": definicion["numero_lista"], "nombre": definicion["nombre_lista"],
                "accion": "crear" if nueva else "reutilizar", "puestos": len(puestos),
                "puestos_por_asociar": faltantes, "presentacion_id": presentacion.pk if presentacion else None,
                "csv_candidatos": definicion["csv_candidatos"],
            })
        return resultado


def configurar_django(proyecto):
    proyecto = Path(proyecto).resolve()
    if not (proyecto / "manage.py").is_file():
        raise ErrorPreparacion("No se encuentra manage.py. Indicá --proyecto con la carpeta VotoUTN (en Docker, /app).")
    sys.path.insert(0, str(proyecto))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()


def main():
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--eleccion", type=int, required=True, help="ID de la elección en preparación.")
    argumentos.add_argument("--claustro", action="append", choices=tuple(CARPETAS), help="Repetible; sin filtro incluye los cuatro.")
    argumentos.add_argument("--aplicar", action="store_true", help="Guardar listas y asociaciones; sin esta opción solo previsualiza.")
    argumentos.add_argument("--proyecto", type=Path, default=BASE.parents[1] / "VotoUTN")
    argumentos.add_argument("--usuario", help="Nombre de usuario de junta para la auditoría (opcional).")
    opciones = argumentos.parse_args()
    try:
        definiciones = leer_definiciones(claustros=opciones.claustro)
        configurar_django(opciones.proyecto)
        from django.contrib.auth import get_user_model
        from django.core.exceptions import ValidationError
        from django.db import DatabaseError
        usuario = None
        if opciones.usuario:
            usuario = get_user_model().objects.filter(username=opciones.usuario, is_active=True).first()
            if usuario is None:
                raise ErrorPreparacion("El usuario de auditoría no existe o está inactivo.")
        resultado = preparar_listas(opciones.eleccion, definiciones, aplicar=opciones.aplicar, usuario=usuario)
    except (ErrorPreparacion, OSError, KeyError) as error:
        argumentos.exit(1, f"Error: {error}\n")
    except ImportError:
        argumentos.exit(1, "Faltan dependencias del proyecto. Ejecutá el script con el Python de la aplicación o dentro de su contenedor.\n")
    except ValidationError as error:
        argumentos.exit(1, "Error de validación; no se guardaron cambios: " + "; ".join(error.messages) + "\n")
    except DatabaseError:
        argumentos.exit(1, "Error de base de datos; no se guardaron cambios. Revisá conexión, migraciones y conflictos de integridad.\n")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    print("Listas preparadas; los candidatos se cargan después mediante sus CSV." if opciones.aplicar else
          "Previsualización: no se guardaron cambios. Agregá --aplicar para crear las listas y asociaciones.")


if __name__ == "__main__":
    main()
