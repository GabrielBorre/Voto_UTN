"""Genera las listas 9 y 3 de No docentes desde el padrón sin autoridades."""

import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
SEGMENTO = RAIZ / "ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500"
ORIGEN = SEGMENTO / "padrones_sin_autoridades_instancia_3"
SALIDA = SEGMENTO / "listas_no_docentes_sin_autoridades"
SEMILLA = 20261118
PUESTOS = (
    ("Consejo Directivo", "Consejero/a directivo/a", 1),
    ("Consejo DASUTeN", "Consejero/a DASUTeN", 2),
)
LISTAS = (
    ("9", "Unión y Participación", "lista_9_union_y_participacion.csv"),
    ("3", "Integración", "lista_3_integracion.csv"),
)
ENCABEZADOS = (
    "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email",
    "claustro", "organo", "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
MULTIPUESTO = ("puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden")


def leer_csv(ruta, separador=","):
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=separador))


def escribir_csv(ruta, campos, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, delimiter=";", extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def clave_persona(fila):
    return fila["Tipo Documento"].strip().upper(), fila["DNI"].strip()


def generar():
    padron = ORIGEN / "padron_no_docentes_sin_autoridades.csv"
    archivo_autoridades = ORIGEN / "autoridades_instancia_3.csv"
    huella = hashlib.sha256(padron.read_bytes()).hexdigest()
    personas = leer_csv(padron)
    por_persona = {clave_persona(fila): fila for fila in personas}
    autoridades = {clave_persona(fila) for fila in leer_csv(archivo_autoridades) if fila["Estado"] == "asignada"}
    if len(por_persona) != len(personas) or any(not clave[1] for clave in por_persona):
        raise ValueError("El padrón tiene documentos repetidos o vacíos.")
    if autoridades & por_persona.keys():
        raise ValueError("El padrón contiene autoridades asignadas.")
    if len(personas) < 8:
        raise ValueError("Se necesitan ocho personas distintas para completar ambas listas.")
    personas = sorted(personas, key=clave_persona)
    random.Random(SEMILLA).shuffle(personas)
    detalle, apoderados, cobertura = [], [], []
    posicion = 0
    for numero, nombre, archivo in LISTAS:
        metadatos = {
            "codigo_presentacion": f"NODOC-{numero}-SEG1", "numero_lista": numero, "nombre_lista": nombre,
            "apoderado_nombre": f"Apoderado externo No docentes Lista {numero}",
            "apoderado_email": f"apoderado.nodocentes{numero}@example.org",
        }
        candidatos = []
        for organo, puesto, cupo in PUESTOS:
            for tipo in ("titular", "suplente"):
                persona = personas[posicion]
                posicion += 1
                fila = {
                    **metadatos, "claustro": "No docentes", "organo": organo, "puesto": puesto,
                    "departamento": "", "tipo_documento": persona["Tipo Documento"],
                    "documento": persona["DNI"], "tipo_candidatura": tipo, "orden": 1,
                }
                candidatos.append(fila)
                detalle.append({
                    **fila, "nombre": persona["Nombre"], "apellido": persona["Apellido"],
                    "legajo": persona["Legajo"], "correo_elector": persona["Mail"],
                })
            cobertura.append({
                "numero_lista": numero, "nombre_lista": nombre, "puesto": puesto,
                "cupo_estandar_titulares": cupo, "cupo_estandar_suplentes": cupo,
                "minimo_50_por_tipo": (cupo + 1) // 2,
                "titulares_propuestos": 1, "suplentes_propuestos": 1,
                "porcentaje_cobertura": 100 // cupo,
            })
        escribir_csv(SALIDA / archivo, MULTIPUESTO, candidatos)
        escribir_csv(SALIDA / "importacion_completa" / archivo, ENCABEZADOS, candidatos)
        apoderados.append({
            **metadatos, "claustro": "No docentes", "archivo": archivo,
            "origen_apoderado": "Ficticio externo al padrón, sin candidatura",
        })
    escribir_csv(SALIDA / "detalle_candidatos.csv", list(detalle[0]), detalle)
    escribir_csv(SALIDA / "listas_y_apoderados.csv", list(apoderados[0]), apoderados)
    escribir_csv(SALIDA / "cobertura.csv", list(cobertura[0]), cobertura)
    validar_resultados(por_persona, autoridades)
    resumen = {
        "padron_origen": str(padron.relative_to(RAIZ)), "sha256_padron_origen": huella,
        "sha256_autoridades_origen": hashlib.sha256(archivo_autoridades.read_bytes()).hexdigest(),
        "semilla": SEMILLA, "personas_disponibles": len(personas), "personas_seleccionadas": 8,
        "personas_no_seleccionadas": len(personas) - 8, "candidatos_por_lista": 4,
        "directivo_por_lista": {"titulares": 1, "suplentes": 1, "cobertura_estandar": 100},
        "dasuten_por_lista": {"titulares": 1, "suplentes": 1, "cobertura_estandar": 50},
        "listas": apoderados,
    }
    (SALIDA / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SALIDA / "LEEME.md").write_text("""# Dos listas de No docentes

- Lista 9 — Unión y Participación: `lista_9_union_y_participacion.csv`.
- Lista 3 — Integración: `lista_3_integracion.csv`.

Cada lista tiene cuatro personas distintas: un titular y un suplente para
Consejo Directivo, y un titular y un suplente para Consejo DASUTeN.
Con los cupos estándar de No docentes, Directivo cubre el 100 % (1+1 de 1+1)
y DASUTeN cubre el 50 % (1+1 de 2+2). Se respeta el mínimo por cuerpo y tipo.
No se incluyen candidatos a Superior ni cargos departamentales.

Origen: padrón de No docentes de segmento_1_500 sin autoridades asignadas de la
foto de instancia 3. Se usan ocho de las 464 personas disponibles; quedan 456.
Ninguna persona se repite entre cargos o listas. Los dos apoderados son ejemplos
ficticios externos al padrón, sin candidatura; reemplazarlos por los datos reales
cuando corresponda. Sus datos están en `listas_y_apoderados.csv`.

## Cargar dentro de una lista

Crear cada lista en No docentes con los datos de `listas_y_apoderados.csv` y
asociarle los puestos Consejero/a directivo/a y Consejero/a DASUTeN.
Desde **Importar por CSV (uno o varios puestos)** cargar el archivo `lista_*.csv`
correspondiente de esta carpeta. Son cuatro candidatos por archivo, con columnas:
`puesto;departamento;tipo_documento;documento;tipo_candidatura;orden`.

Los dos puestos son generales: departamento queda vacío. El orden es 1 para
cada combinación de puesto y tipo. Se usa UTF-8 con BOM y punto y coma.
Los puestos deben estar habilitados para No docentes en la elección.

Como alternativa, los archivos de `importacion_completa/` incluyen las trece
columnas de presentación, apoderado y candidatos para cargar desde
`/gestion/elecciones/<id>/candidaturas/importar/`. Elegir una vía por lista.

`detalle_candidatos.csv` permite revisar nombres, documentos y legajos;
`cobertura.csv` informa las cantidades por cuerpo, y `resumen.json` registra
el origen, sus huellas SHA-256 y la semilla de selección.

Regenerar con `python scripts/generar_listas_no_docentes_demo.py`.
Se generan archivos de prueba: no se cambia el padrón, los parámetros ni la base.
""", encoding="utf-8")
    if hashlib.sha256(padron.read_bytes()).hexdigest() != huella:
        raise ValueError("El padrón de origen cambió durante la generación.")
    print(json.dumps(resumen, ensure_ascii=True, indent=2))


def validar_resultados(por_persona, autoridades):
    utilizados = set()
    for numero, nombre, archivo in LISTAS:
        filas = leer_csv(SALIDA / "importacion_completa" / archivo, ";")
        if len(filas) != 4 or any(set(fila) != set(ENCABEZADOS) for fila in filas):
            raise ValueError("Cantidad de filas o columnas incorrecta.")
        conteos = Counter((fila["puesto"], fila["tipo_candidatura"]) for fila in filas)
        if conteos != Counter({(puesto, tipo): 1 for _, puesto, _ in PUESTOS for tipo in ("titular", "suplente")}):
            raise ValueError("No hay exactamente un titular y un suplente por cuerpo.")
        for fila in filas:
            clave = fila["tipo_documento"], fila["documento"]
            if clave not in por_persona or clave in autoridades or clave in utilizados:
                raise ValueError("Persona ajena al padrón, autoridad o repetida.")
            utilizados.add(clave)
            if fila["departamento"] or fila["orden"] != "1" or fila["claustro"] != "No docentes":
                raise ValueError("Alcance, orden o claustro incorrecto.")
            if fila["numero_lista"] != numero or fila["nombre_lista"] != nombre:
                raise ValueError("Metadatos de lista incorrectos.")
        if leer_csv(SALIDA / archivo, ";") != [{k: fila[k] for k in MULTIPUESTO} for fila in filas]:
            raise ValueError("Las variantes CSV difieren.")
    if len(utilizados) != 8:
        raise ValueError("Se esperaban ocho personas distintas.")


if __name__ == "__main__":
    generar()
