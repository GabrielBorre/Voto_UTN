"""Genera dos listas de graduados completas desde el padrón sin autoridades."""

import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
SEGMENTO = RAIZ / "ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500"
ORIGEN = SEGMENTO / "padrones_sin_autoridades_instancia_3"
SALIDA = SEGMENTO / "listas_graduados_sin_autoridades"
SEMILLA = 20261118
DEPARTAMENTOS = {
    "K": "Ingeniería en Sistemas de Información",
    "I": "Ingeniería Industrial",
    "R": "Ingeniería Electrónica",
}
PUESTOS = (
    ("Consejo Superior", "Consejero/a Superior", "", 5),
    ("Consejo Directivo", "Consejero/a directivo/a", "", 5),
    *(("Consejo Departamental", "Consejero/a departamental", codigo, 2) for codigo in DEPARTAMENTOS),
    ("Consejo Departamental", "Consejero/a Ciencias Básicas", "", 2),
)
LISTAS = (
    {"codigo_presentacion": "GRAD-19-SEG1", "numero_lista": "19", "nombre_lista": "21 de septiembre",
     "apoderado_nombre": "Apoderado externo Graduados Lista 19", "apoderado_email": "apoderado.graduados19@example.org",
     "archivo": "lista_19_19_de_agosto.csv"},
    {"codigo_presentacion": "GRAD-3-SEG1", "numero_lista": "3", "nombre_lista": "Graduados Club",
     "apoderado_nombre": "Apoderado externo Graduados Lista 3", "apoderado_email": "apoderado.graduados3@example.org",
     "archivo": "lista_3_club_del_graduado.csv"},
)
ENCABEZADOS = (
    "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email",
    "claustro", "organo", "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
ENCABEZADOS_MULTIPUESTO = (
    "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)


def leer_csv(ruta, delimitador=","):
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=delimitador))


def escribir_csv(ruta, campos, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, delimiter=";", extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def clave_persona(fila):
    return fila["Tipo Documento"].strip().upper(), fila["DNI"].strip()


def generar():
    padron = ORIGEN / "padron_graduados_sin_autoridades.csv"
    archivo_autoridades = ORIGEN / "autoridades_instancia_3.csv"
    huella_padron = hashlib.sha256(padron.read_bytes()).hexdigest()
    filas = leer_csv(padron)
    por_persona = {clave_persona(fila): fila for fila in filas}
    autoridades = {clave_persona(fila) for fila in leer_csv(archivo_autoridades) if fila["Estado"] == "asignada"}
    if len(por_persona) != len(filas) or any(not clave[1] for clave in por_persona):
        raise ValueError("El padrón de graduados tiene documentos repetidos o vacíos.")
    if autoridades & por_persona.keys():
        raise ValueError("El padrón de origen contiene autoridades.")
    disponibles = Counter(fila["Depto/Carrera"] for fila in filas)
    for codigo in DEPARTAMENTOS:
        if disponibles[codigo] < 8:
            raise ValueError(f"El departamento {codigo} no tiene ocho personas para completar ambas listas.")
    if len(filas) < 72:
        raise ValueError("Se necesitan 72 personas distintas para completar las dos listas.")

    generador = random.Random(SEMILLA)
    utilizados = set()
    seleccion = {}
    # Reservar primero los puestos departamentales evita consumir su padrón
    # limitado en los puestos generales, abiertos a cualquier departamento.
    for codigo in DEPARTAMENTOS:
        personas = sorted((fila for fila in filas if fila["Depto/Carrera"] == codigo), key=clave_persona)
        generador.shuffle(personas)
        for indice, lista in enumerate(LISTAS):
            elegidas = personas[indice * 4:(indice + 1) * 4]
            seleccion[(lista["numero_lista"], "Consejero/a departamental", codigo)] = elegidas
            utilizados.update(clave_persona(fila) for fila in elegidas)
    resto = sorted((fila for fila in filas if clave_persona(fila) not in utilizados), key=clave_persona)
    generador.shuffle(resto)
    inicio = 0
    for lista in LISTAS:
        for _organo, puesto, codigo, cupo in PUESTOS:
            if codigo:
                continue
            elegidas = resto[inicio:inicio + cupo * 2]
            inicio += cupo * 2
            seleccion[(lista["numero_lista"], puesto, codigo)] = elegidas
            utilizados.update(clave_persona(fila) for fila in elegidas)

    detalle = []
    cobertura = []
    resumen_listas = []
    apoderados = []
    for lista in LISTAS:
        candidatos = []
        metadatos = {campo: lista[campo] for campo in ENCABEZADOS[:5]}
        for organo, puesto, codigo, cupo in PUESTOS:
            personas = seleccion[(lista["numero_lista"], puesto, codigo)]
            if len(personas) != 2 * cupo:
                raise ValueError("No se pudo completar un puesto.")
            for indice, persona in enumerate(personas):
                tipo = "titular" if indice < cupo else "suplente"
                candidato = {
                    **metadatos, "claustro": "Graduados", "organo": organo, "puesto": puesto,
                    "departamento": DEPARTAMENTOS.get(codigo, ""),
                    "tipo_documento": persona["Tipo Documento"], "documento": persona["DNI"],
                    "tipo_candidatura": tipo, "orden": indice % cupo + 1,
                }
                candidatos.append(candidato)
                detalle.append({
                    **candidato, "nombre": persona["Nombre"], "apellido": persona["Apellido"],
                    "legajo": persona["Legajo"], "departamento_elector": persona["Depto/Carrera"],
                    "correo_elector": persona["Mail"],
                })
            cobertura.append({
                "numero_lista": lista["numero_lista"], "nombre_lista": lista["nombre_lista"],
                "organo": organo, "puesto": puesto, "departamento": DEPARTAMENTOS.get(codigo, ""),
                "cupo_titulares": cupo, "cupo_suplentes": cupo,
                "minimo_titulares_50": (cupo + 1) // 2, "minimo_suplentes_50": (cupo + 1) // 2,
                "titulares_propuestos": cupo, "suplentes_propuestos": cupo,
                "porcentaje_cobertura": 100,
            })
        escribir_csv(SALIDA / lista["archivo"], ENCABEZADOS_MULTIPUESTO, candidatos)
        escribir_csv(SALIDA / "importacion_completa" / lista["archivo"], ENCABEZADOS, candidatos)
        apoderados.append({**metadatos, "claustro": "Graduados", "origen_apoderado": "Ficticio externo al padrón"})
        resumen_listas.append({
            **metadatos, "archivo_importacion_completa": "importacion_completa/" + lista["archivo"],
            "archivo_multipuesto": lista["archivo"], "candidatos": len(candidatos),
            "titulares": sum(fila["tipo_candidatura"] == "titular" for fila in candidatos),
            "suplentes": sum(fila["tipo_candidatura"] == "suplente" for fila in candidatos),
            "puestos": len(PUESTOS), "cobertura_por_puesto": 100,
            "departamentos_origen": dict(sorted(Counter(
                por_persona[(fila["tipo_documento"], fila["documento"])]["Depto/Carrera"]
                for fila in candidatos
            ).items())),
        })
    escribir_csv(SALIDA / "detalle_candidatos.csv", tuple(ENCABEZADOS) + (
        "nombre", "apellido", "legajo", "departamento_elector", "correo_elector",
    ), detalle)
    escribir_csv(SALIDA / "listas_y_apoderados.csv", list(apoderados[0]), apoderados)
    escribir_csv(SALIDA / "cobertura.csv", list(cobertura[0]), cobertura)

    resumen = {
        "padron_origen": str(padron.relative_to(RAIZ)), "sha256_padron_origen": huella_padron,
        "sha256_autoridades_origen": hashlib.sha256(archivo_autoridades.read_bytes()).hexdigest(),
        "semilla_seleccion": SEMILLA, "porcentaje_minimo": 50, "porcentaje_aplicado": 100,
        "personas_disponibles": len(filas), "candidatos_distintos": len(utilizados),
        "personas_no_seleccionadas": len(filas) - len(utilizados),
        "departamentos": [{"codigo": codigo, "nombre": nombre, "personas_disponibles": disponibles[codigo],
                           "personas_necesarias_ambas_listas": 8} for codigo, nombre in DEPARTAMENTOS.items()],
        "apoderados_externos": True, "listas": resumen_listas,
        "distribucion_total_departamentos": dict(sorted(Counter(
            fila["departamento_elector"] for fila in detalle
        ).items())),
    }
    (SALIDA / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lineas = [
        "# Dos listas de candidatos de graduados", "",
        "Listas 19 — 21 de septiembre y 3 — Graduados Club.",
        "Origen: padrón de graduados de segmento_1_500 sin autoridades de la foto de instancia 3.", "",
        "El mínimo solicitado es 50 % por cuerpo. Los datos permiten cubrir el 100 % en ambas listas:", "",
        "| Cuerpo / alcance | Titulares por lista | Suplentes por lista | Cobertura |",
        "|---|---:|---:|---:|",
        "| Consejo Superior, cualquier departamento | 5 | 5 | 100 % |",
        "| Consejo Directivo, cualquier departamento | 5 | 5 | 100 % |",
        "| Consejo Departamental — Sistemas (K) | 2 | 2 | 100 % |",
        "| Consejo Departamental — Industrial (I) | 2 | 2 | 100 % |",
        "| Consejo Departamental — Electrónica (R) | 2 | 2 | 100 % |",
        "| Ciencias Básicas, cualquier departamento | 2 | 2 | 100 % |", "",
        "Cada lista contiene 36 personas: 18 titulares y 18 suplentes. Se usan 72 personas distintas,",
        f"sin repetirlas entre cargos ni entre listas; quedan {resumen['personas_no_seleccionadas']} graduados sin seleccionar.",
        f"Hay {disponibles['K']} personas disponibles de K, {disponibles['I']} de I y {disponibles['R']} de R. Cada departamento necesita ocho",
        "para completar ambas listas, por lo que alcanzan los tres departamentos.", "",
        "Los apoderados son datos ficticios externos al padrón y no aparecen como candidatos.",
        "Sus nombres y correos de ejemplo se informan en listas_y_apoderados.csv.", "",
        "## Cargar candidatos dentro de una lista", "",
        "Crear cada lista en Graduados con los datos de listas_y_apoderados.csv y asociarle los seis puestos.",
        "En la pestaña Importar por CSV (uno o varios puestos), cargar lista_19_19_de_agosto.csv",
        "o lista_3_club_del_graduado.csv, según la lista. Cada archivo tiene 36 candidatos y seis columnas:",
        "`puesto;departamento;tipo_documento;documento;tipo_candidatura;orden`.",
        "Los puestos deben estar habilitados para Graduados en la elección y sus cupos deben ser los indicados arriba.", "",
        "## Alternativa de importación completa", "",
        "Los archivos de importacion_completa/ incluyen los datos de la presentación, del apoderado y los seis puestos.",
        "Se cargan desde `/gestion/elecciones/<id>/candidaturas/importar/`.",
        "Elegir esta vía o la carga dentro de cada lista.", "",
        "Los departamentos de los puestos generales quedan vacíos; para los departamentales se usa el nombre completo.",
        "Los archivos usan UTF-8 con BOM y separador punto y coma, según las plantillas de la aplicación.", "",
        "## Revisión y regeneración", "",
        "detalle_candidatos.csv contiene nombres, documentos, legajos, departamentos y la candidatura de cada persona.",
        "cobertura.csv muestra los cupos completos, los mínimos redondeados del 50 % y la cobertura propuesta.",
        "resumen.json registra el origen, las huellas SHA-256 y la semilla de selección.", "",
        "```powershell", "python scripts/generar_listas_graduados_demo.py", "```", "",
        "Se generan archivos de prueba; no se crean listas ni candidatos en una base de datos.", "",
    ]
    (SALIDA / "LEEME.md").write_text("\n".join(lineas), encoding="utf-8")
    validar_resultados(por_persona, autoridades)
    print(json.dumps(resumen, ensure_ascii=True, indent=2))


def validar_resultados(por_persona, autoridades):
    documentos = set()
    for lista in LISTAS:
        filas = leer_csv(SALIDA / "importacion_completa" / lista["archivo"], ";")
        if len(filas) != 36 or len(filas[0]) != len(ENCABEZADOS):
            raise ValueError("Cantidad de candidatos o columnas incorrecta.")
        conteos = Counter((fila["puesto"], fila["departamento"], fila["tipo_candidatura"]) for fila in filas)
        for fila in filas:
            clave = (fila["tipo_documento"], fila["documento"])
            if clave in documentos or clave in autoridades or clave not in por_persona:
                raise ValueError("Identidad repetida, excluida o ajena al padrón de origen.")
            documentos.add(clave)
            if fila["departamento"] and DEPARTAMENTOS[por_persona[clave]["Depto/Carrera"]] != fila["departamento"]:
                raise ValueError("El candidato departamental no pertenece a ese departamento.")
        for _organo, puesto, codigo, cupo in PUESTOS:
            for tipo in ("titular", "suplente"):
                if conteos[(puesto, DEPARTAMENTOS.get(codigo, ""), tipo)] != cupo:
                    raise ValueError("Un puesto no tiene su cupo completo.")
                ordenes = [int(fila["orden"]) for fila in filas if fila["puesto"] == puesto
                           and fila["departamento"] == DEPARTAMENTOS.get(codigo, "")
                           and fila["tipo_candidatura"] == tipo]
                if ordenes != list(range(1, cupo + 1)):
                    raise ValueError("El orden de los candidatos no es consecutivo.")
        multiples = leer_csv(SALIDA / lista["archivo"], ";")
        if multiples != [{campo: fila[campo] for campo in ENCABEZADOS_MULTIPUESTO} for fila in filas]:
            raise ValueError("La variante multipuesto no coincide con la importación completa.")
    if len(documentos) != 72:
        raise ValueError("Se esperaban 72 personas distintas.")


if __name__ == "__main__":
    generar()
