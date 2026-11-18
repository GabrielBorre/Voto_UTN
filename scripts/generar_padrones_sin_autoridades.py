"""Cruza una foto SQL con los CSV, sin ejecutar SQL ni modificar los originales."""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
TABLAS = {
    "elecciones_eleccion", "elecciones_claustro", "elecciones_eleccionclaustro",
    "elecciones_eleccionclaustrodepartamento", "elecciones_elector",
    "elecciones_registropadron", "elecciones_asignacionautoridad",
    "elecciones_mesa", "elecciones_departamento", "elecciones_turno",
}
PADRONES = {
    "padron_estudiantes.csv": "Estudiantes",
    "padron_docentes.csv": "Docentes",
    "padron_graduados.csv": "Graduados",
    "padron_no_docentes.csv": "No docentes",
}
EXCLUSIONES_ADICIONALES = {
    "padron_estudiantes.csv": {("DNI", "38999222")},
}


def descodificar_campo(valor):
    if valor == r"\N":
        return None
    escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}

    def reemplazar(coincidencia):
        campo = coincidencia[1]
        if re.fullmatch(r"[0-7]{1,3}", campo):
            return chr(int(campo, 8))
        if campo.startswith("x") and len(campo) > 1:
            return chr(int(campo[1:], 16))
        return escapes.get(campo, campo)

    return re.sub(r"\\([0-7]{1,3}|x[0-9a-fA-F]{1,2}|.)", reemplazar, valor)


def leer_foto(ruta):
    contenido = ruta.read_bytes()
    huellas = json.loads(ruta.with_name("huellas.json").read_text(encoding="utf-8-sig"))
    huella_original = hashlib.sha256(contenido).hexdigest()
    huella_lf = hashlib.sha256(contenido.replace(b"\r\n", b"\n")).hexdigest()
    esperada = huellas["postgres_sha256"].lower()
    if huellas["instancia"] != 3 or esperada not in (huella_original, huella_lf):
        raise ValueError("La foto no corresponde a instancia 3 o no coincide con su SHA-256.")
    tablas = {}
    tabla = None
    columnas = []
    for linea in contenido.decode("utf-8-sig").splitlines():
        inicio = re.fullmatch(r"COPY public\.([a-z_]+) \((.+)\) FROM stdin;", linea)
        if inicio:
            tabla = inicio[1] if inicio[1] in TABLAS else None
            columnas = inicio[2].split(", ")
            if tabla:
                if tabla in tablas:
                    raise ValueError(f"Bloque COPY duplicado: {tabla}.")
                tablas[tabla] = []
        elif linea == r"\.":
            tabla = None
        elif tabla:
            valores = linea.split("\t")
            if len(valores) != len(columnas):
                raise ValueError(f"Cantidad de campos incorrecta en {tabla}.")
            tablas[tabla].append(dict(zip(columnas, map(descodificar_campo, valores))))
    if TABLAS - tablas.keys():
        raise ValueError(f"Faltan tablas necesarias: {sorted(TABLAS - tablas.keys())}.")
    return tablas, huellas, huella_original, huella_lf


def identidad(tipo, documento):
    tipo = (tipo or "DNI").strip().upper()
    documento = (documento or "").strip()
    if not documento:
        raise ValueError("Se encontro un registro sin documento.")
    return tipo, documento


def escribir_csv(ruta, columnas, filas, *, codificacion="utf-8", salto="\r\n"):
    with ruta.open("w", encoding=codificacion, newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, lineterminator=salto)
        escritor.writeheader()
        escritor.writerows(filas)


def generar(foto, padrones, salida, eleccion_id=None):
    tablas, huellas, huella_original, huella_lf = leer_foto(foto)
    elecciones = tablas["elecciones_eleccion"]
    if eleccion_id is not None:
        elecciones = [fila for fila in elecciones if fila["id"] == str(eleccion_id)]
    if len(elecciones) != 1:
        raise ValueError("Indicar --eleccion para seleccionar una unica eleccion de la foto.")
    eleccion = elecciones[0]
    indices = {nombre: {fila["id"]: fila for fila in filas} for nombre, filas in tablas.items()}
    autoridades = []
    claves_asignadas = set()
    for asignacion in tablas["elecciones_asignacionautoridad"]:
        registro = indices["elecciones_registropadron"][asignacion["registro_padron_id"]]
        if registro["eleccion_id"] != eleccion["id"]:
            continue
        if asignacion["estado"] not in ("asignada", "rechazada"):
            raise ValueError(f"Estado de autoridad desconocido: {asignacion['estado']}.")
        elector = indices["elecciones_elector"][registro["elector_id"]]
        clave = identidad(elector["tipo_documento"], registro["dni"])
        if clave != identidad(elector["tipo_documento"], elector["dni"]):
            raise ValueError("El documento del elector difiere del registro de padron de la foto.")
        alcance = indices["elecciones_eleccionclaustrodepartamento"][registro["eleccion_claustro_departamento_id"]]
        claustro_eleccion = indices["elecciones_eleccionclaustro"][alcance["eleccion_claustro_id"]]
        claustro = indices["elecciones_claustro"][claustro_eleccion["claustro_id"]]["nombre"]
        mesa = indices["elecciones_mesa"][asignacion["mesa_id"]]
        alcance_mesa = indices["elecciones_eleccionclaustrodepartamento"][mesa["eleccion_claustro_departamento_id"]]
        departamento = indices["elecciones_departamento"].get(alcance_mesa["departamento_id"], {})
        prefijo = departamento.get("codigo", "")
        codigo = (prefijo + "-" if prefijo else "") + f"{int(mesa['numero']):03d}"
        autoridades.append({
            "Claustro": claustro, "Tipo Documento": clave[0], "DNI": clave[1],
            "Legajo": registro["legajo"], "Nombre": elector["nombre"], "Apellido": elector["apellido"],
            "Mesa": codigo, "Tipo mesa": "Especial" if mesa["es_especial"] == "t" else "Ordinaria",
            "Turno": indices["elecciones_turno"][asignacion["turno_id"]]["nombre"],
            "Estado": asignacion["estado"], "Tipo autoridad": asignacion["tipo"],
            "Archivo padron": "", "Filas coincidentes": 0, "Filas excluidas": 0,
        })
        if asignacion["estado"] == "asignada":
            claves_asignadas.add(clave)

    preparados = []
    claves_en_csv = set()
    for nombre, claustro in PADRONES.items():
        ruta = padrones / nombre
        datos = ruta.read_bytes()
        lector = csv.DictReader(io.StringIO(datos.decode("utf-8-sig"), newline=""))
        columnas = lector.fieldnames
        if not columnas or not {"DNI", "Tipo Documento", "Legajo", "Depto/Carrera"} <= set(columnas):
            raise ValueError(f"Encabezado de padron no reconocido: {nombre}.")
        filas = list(lector)
        if any(None in fila or any(valor is None for valor in fila.values()) for fila in filas):
            raise ValueError(f"Filas con cantidad de campos incorrecta: {nombre}.")
        claves = [identidad(fila["Tipo Documento"], fila["DNI"]) for fila in filas]
        claves_en_csv.update(claves)
        adicionales = EXCLUSIONES_ADICIONALES.get(nombre, set())
        claves_excluidas = claves_asignadas | adicionales
        conservadas = [fila for fila, clave in zip(filas, claves) if clave not in claves_excluidas]
        excluidas = [fila for fila, clave in zip(filas, claves) if clave in claves_excluidas]
        conteos = Counter(claves)
        for autoridad in autoridades:
            clave = identidad(autoridad["Tipo Documento"], autoridad["DNI"])
            if conteos[clave]:
                if autoridad["Claustro"] != claustro or autoridad["Archivo padron"]:
                    raise ValueError("Una autoridad coincide con un padron de otro claustro.")
                autoridad["Archivo padron"] = nombre
                autoridad["Filas coincidentes"] = conteos[clave]
                autoridad["Filas excluidas"] = conteos[clave] if clave in claves_excluidas else 0
        resumen = {
            "archivo_original": nombre, "claustro": claustro,
            "archivo_generado": ruta.stem + "_sin_autoridades.csv",
            "filas_originales": len(filas), "personas_originales": len(set(claves)),
            "filas_excluidas": len(excluidas),
            "personas_excluidas": len(set(claves) & claves_excluidas),
            "personas_excluidas_por_autoridad": len(set(claves) & claves_asignadas),
            "personas_excluidas_adicionalmente": len((set(claves) & adicionales) - claves_asignadas),
            "exclusiones_adicionales": [
                {"tipo_documento": tipo, "documento": documento}
                for tipo, documento in sorted(adicionales)
            ],
            "filas_generadas": len(conservadas),
            "personas_generadas": len(set(claves) - claves_excluidas),
            "distribucion_departamentos": dict(sorted(Counter(
                fila["Depto/Carrera"] or "Sin departamento" for fila in conservadas
            ).items())),
            "sha256_original": hashlib.sha256(datos).hexdigest(),
        }
        preparados.append((resumen, columnas, conservadas, datos))

    if salida.resolve() == padrones.resolve():
        raise ValueError("La carpeta de salida debe ser distinta de los padrones originales.")
    salida.mkdir(parents=True, exist_ok=True)
    for resumen, columnas, filas, datos in preparados:
        destino = salida / resumen["archivo_generado"]
        escribir_csv(destino, columnas, filas,
                     codificacion="utf-8-sig" if datos.startswith(b"\xef\xbb\xbf") else "utf-8",
                     salto="\r\n" if b"\r\n" in datos else "\n")
        resumen["sha256_generado"] = hashlib.sha256(destino.read_bytes()).hexdigest()

    autoridades.sort(key=lambda fila: (fila["Claustro"], fila["Mesa"], fila["Turno"], fila["DNI"]))
    if autoridades:
        escribir_csv(salida / "autoridades_instancia_3.csv", list(autoridades[0]), autoridades)
    resumen_final = {
        "foto": str(foto.relative_to(RAIZ) if foto.is_relative_to(RAIZ) else foto),
        "capturada_en": huellas["capturada_en"], "instancia": 3,
        "eleccion": {campo: eleccion[campo] for campo in ("id", "nombre", "estado")},
        "sha256_foto_archivo": huella_original, "sha256_foto_lf": huella_lf,
        "criterio": "Excluir todas las filas de personas con autoridad asignada en la foto y las exclusiones adicionales indicadas, por tipo y numero de documento.",
        "autoridades_por_estado": dict(Counter(fila["Estado"] for fila in autoridades)),
        "personas_autoridades_asignadas": len(claves_asignadas),
        "autoridades_asignadas_sin_coincidencia": [
            {"tipo_documento": tipo, "documento": documento}
            for tipo, documento in sorted(claves_asignadas - claves_en_csv)
        ],
        "padrones": [resumen for resumen, *_ in preparados],
    }
    (salida / "resumen.json").write_text(json.dumps(resumen_final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lineas = [
        "# Padrones sin autoridades de la instancia 3", "",
        f"Origen: `{resumen_final['foto']}`, foto del {resumen_final['capturada_en']}.",
        f"Eleccion: {eleccion['nombre']} (id {eleccion['id']}, {eleccion['estado']}).", "",
        "Se excluyen personas con designacion en estado `asignada`, mediante tipo y numero de documento.",
        "Las designaciones `rechazada` no excluyen por si solas a la persona.",
        "Exclusion adicional solicitada en Estudiantes: Carlos Gomez, DNI 38999222.",
        "Si una persona aparece en varios departamentos, se eliminan todas sus filas.",
        "Se conservan las columnas, valores, orden y formato CSV de las filas restantes. Los originales no se modifican.", "",
        "| Claustro | Filas originales | Personas excluidas | Filas excluidas | Filas nuevas | Personas restantes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for resumen, *_ in preparados:
        lineas.append("| " + " | ".join(str(resumen[campo]) for campo in (
            "claustro", "filas_originales", "personas_excluidas", "filas_excluidas", "filas_generadas", "personas_generadas",
        )) + " |")
    lineas += ["", "`autoridades_instancia_3.csv` detalla las designaciones, sus mesas, turnos, estados y coincidencias.",
               "`resumen.json` incluye cantidades, distribucion por departamento y huellas SHA-256.", "",
               "La huella de la foto coincide con `huellas.json` al normalizar los finales de linea a LF.",
               "La lectura del SQL es directa: no se restaura ni se modifica ninguna base de datos.", "",
               "Para regenerar desde la raiz del repositorio:", "", "```powershell",
               "python scripts/generar_padrones_sin_autoridades.py", "```", ""]
    (salida / "LEEME.md").write_text("\n".join(lineas), encoding="utf-8")
    print(json.dumps({"salida": str(salida), "padrones": resumen_final["padrones"],
                      "autoridades_por_estado": resumen_final["autoridades_por_estado"],
                      "autoridades_sin_coincidencia": len(resumen_final["autoridades_asignadas_sin_coincidencia"])},
                     ensure_ascii=True, indent=2))


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--foto", type=Path, default=RAIZ / ".instancias/foto-instancia-3/postgres.sql")
    argumentos.add_argument("--padrones", type=Path, default=RAIZ / "ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500")
    argumentos.add_argument("--salida", type=Path)
    argumentos.add_argument("--eleccion", type=int)
    opciones = argumentos.parse_args()
    generar(opciones.foto, opciones.padrones,
            opciones.salida or opciones.padrones / "padrones_sin_autoridades_instancia_3", opciones.eleccion)
