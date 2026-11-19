"""Genera dos familias de tres sublistas docentes y dos listas DASUTeN.

Solo escribe archivos de prueba. No importa datos a la aplicación.
"""

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
SEGMENTO = RAIZ / "ESCENARIOS_PRUEBA_ELECTORAL/segmento_1_500"
ORIGEN = SEGMENTO / "padrones_sin_autoridades_instancia_3"
SALIDA = SEGMENTO / "listas_docentes_sin_autoridades"
SEMILLA = 20261118
DEPARTAMENTOS = {
    "K": ("Sistemas", "sistemas", "Ingeniería en Sistemas de Información"),
    "I": ("Industrial", "industrial", "Ingeniería Industrial"),
    "R": ("Electrónica", "electronica", "Ingeniería Electrónica"),
}
GRUPOS = (("19", "19 de agosto", "19_de_agosto"), ("2", "Integración", "integracion"))
SUPERIOR = "Consejero/a Superior"
DIRECTIVO = "Consejero/a directivo/a"
DEPARTAMENTAL = "Consejero/a departamental"
DASUTEN = "Consejero/a DASUTeN"
ENCABEZADOS = (
    "codigo_presentacion", "numero_lista", "nombre_lista", "apoderado_nombre", "apoderado_email",
    "claustro", "organo", "puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden",
)
MULTIPUESTO = ("puesto", "departamento", "tipo_documento", "documento", "tipo_candidatura", "orden")


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


def puestos(codigo, cupo_directivo):
    if codigo == "DASUTEN":
        return (("Consejo DASUTeN", DASUTEN, "", 2),)
    return (("Consejo Superior", SUPERIOR, "", 15),
            ("Consejo Directivo", DIRECTIVO, "", cupo_directivo),
            ("Consejo Departamental", DEPARTAMENTAL, codigo, 5))


def generar(cupo_directivo):
    padron = ORIGEN / "padron_docentes_sin_autoridades.csv"
    archivo_autoridades = ORIGEN / "autoridades_instancia_3.csv"
    huella = hashlib.sha256(padron.read_bytes()).hexdigest()
    por_persona = defaultdict(list)
    for fila in leer_csv(padron):
        clave = clave_persona(fila)
        if not clave[1]:
            raise ValueError("El padrón contiene un documento vacío.")
        por_persona[clave].append(fila)
    autoridades = {clave_persona(fila) for fila in leer_csv(archivo_autoridades) if fila["Estado"] == "asignada"}
    if autoridades & por_persona.keys():
        raise ValueError("El padrón de origen contiene autoridades asignadas.")
    principales = {}
    for clave, registros in por_persona.items():
        candidatos_principales = [r for r in registros if r["Depto/Carrera"] == r["Departamento Principal"]]
        if len(candidatos_principales) != 1:
            raise ValueError(f"La persona {clave} no tiene un único registro principal.")
        principales[clave] = candidatos_principales[0]
        if len({r["Depto/Carrera"] for r in registros}) != len(registros):
            raise ValueError(f"La persona {clave} repite un registro departamental.")

    generador = random.Random(SEMILLA)
    utilizados = set()
    seleccion = {}
    disponibles_departamento = {}
    # Reservar las departamentales antes de seleccionar los puestos generales.
    for codigo in DEPARTAMENTOS:
        disponibles_departamento[codigo] = sum(
            any(r["Depto/Carrera"] == codigo for r in registros) for registros in por_persona.values()
        )
        personas = sorted(k for k, registros in por_persona.items()
                          if any(r["Depto/Carrera"] == codigo for r in registros) and k not in utilizados)
        if len(personas) < 20:
            raise ValueError(f"No alcanzan 20 docentes de {codigo} para ambas departamentales completas.")
        generador.shuffle(personas)
        for indice, (numero, _nombre, _slug) in enumerate(GRUPOS):
            elegidas = personas[indice * 10:(indice + 1) * 10]
            seleccion[(numero, codigo, DEPARTAMENTAL)] = elegidas
            utilizados.update(elegidas)

    resto = sorted(por_persona.keys() - utilizados)
    generador.shuffle(resto)
    posicion = 0

    def tomar(cantidad, utilizar=True):
        nonlocal posicion
        elegidas = resto[posicion:posicion + cantidad]
        if len(elegidas) != cantidad:
            raise ValueError("No hay suficientes personas distintas para completar los puestos generales.")
        posicion += cantidad
        if utilizar:
            utilizados.update(elegidas)
        return elegidas

    for numero, _nombre, _slug in GRUPOS:
        # Una nómina de Superior por familia, compartida sin alterar tipo ni orden.
        seleccion[(numero, "COMUN", SUPERIOR)] = tomar(30)
        for codigo in (*DEPARTAMENTOS, "DASUTEN"):
            # Saltar la antigua selección de Directivo-DASUTeN mantiene las
            # restantes nóminas sin cambios al retirar esas ocho candidaturas.
            elegidas = tomar(cupo_directivo * 2, utilizar=codigo != "DASUTEN")
            if codigo != "DASUTEN":
                seleccion[(numero, codigo, DIRECTIVO)] = elegidas
        seleccion[(numero, "DASUTEN", DASUTEN)] = tomar(4)

    detalle, cobertura, presentaciones = [], [], []
    for numero, nombre_grupo, slug_grupo in GRUPOS:
        for codigo in (*DEPARTAMENTOS, "DASUTEN"):
            etiqueta, slug = DEPARTAMENTOS[codigo][:2] if codigo in DEPARTAMENTOS else ("DASUTeN", "dasuten")
            archivo = f"lista_{numero}_{slug_grupo}_{slug}.csv"
            metadatos = {
                "codigo_presentacion": f"DOC-{numero}-{codigo}-SEG1", "numero_lista": numero,
                "nombre_lista": f"{nombre_grupo} - {etiqueta}",
                "apoderado_nombre": f"Apoderado externo Docentes {numero} {etiqueta}",
                "apoderado_email": f"apoderado.docentes{numero}.{slug}@example.org",
            }
            filas = []
            for organo, puesto, alcance, cupo in puestos(codigo, cupo_directivo):
                claves = seleccion[(numero, "COMUN" if puesto == SUPERIOR else codigo, puesto)]
                for indice, clave in enumerate(claves):
                    persona = principales[clave]
                    fila = {
                        **metadatos, "claustro": "Docentes", "organo": organo, "puesto": puesto,
                        "departamento": DEPARTAMENTOS[alcance][2] if alcance else "",
                        "tipo_documento": clave[0], "documento": clave[1],
                        "tipo_candidatura": "titular" if indice < cupo else "suplente",
                        "orden": indice % cupo + 1,
                    }
                    filas.append(fila)
                    detalle.append({
                        **fila, "nombre": persona["Nombre"], "apellido": persona["Apellido"],
                        "legajo": persona["Legajo"], "departamento_principal": persona["Departamento Principal"],
                        "departamentos_padron": ",".join(sorted(r["Depto/Carrera"] for r in por_persona[clave])),
                        "correo_elector": persona["Mail"], "grupo": nombre_grupo,
                    })
                cupo_referencia = cupo
                cobertura.append({
                    "codigo_presentacion": metadatos["codigo_presentacion"], "puesto": puesto,
                    "departamento": DEPARTAMENTOS[alcance][2] if alcance else "",
                    "titulares_propuestos": cupo, "suplentes_propuestos": cupo,
                    "cupo_referencia_titulares": cupo_referencia, "cupo_referencia_suplentes": cupo_referencia,
                    "minimo_50_por_tipo": (cupo_referencia + 1) // 2,
                    "porcentaje_referencia": cupo * 100 // cupo_referencia,
                })
            escribir_csv(SALIDA / archivo, MULTIPUESTO, filas)
            escribir_csv(SALIDA / "importacion_completa" / archivo, ENCABEZADOS, filas)
            presentaciones.append({
                **metadatos, "claustro": "Docentes", "grupo": nombre_grupo, "alcance": etiqueta,
                "tipo_lista": "departamental" if codigo in DEPARTAMENTOS else "Solo DASUTeN",
                "archivo": archivo, "filas_candidaturas": len(filas),
                "personas_superior_compartidas": 30 if codigo in DEPARTAMENTOS else 0,
                "apoderado_origen": "Ficticio externo al padrón, sin candidatura",
            })

    escribir_csv(SALIDA / "detalle_candidatos.csv", list(detalle[0]), detalle)
    escribir_csv(SALIDA / "listas_y_apoderados.csv", list(presentaciones[0]), presentaciones)
    escribir_csv(SALIDA / "cobertura.csv", list(cobertura[0]), cobertura)
    resumen = {
        "padron_origen": str(padron.relative_to(RAIZ)), "sha256_padron_origen": huella,
        "sha256_autoridades_origen": hashlib.sha256(archivo_autoridades.read_bytes()).hexdigest(),
        "semilla": SEMILLA, "porcentaje_minimo_solicitado": 50,
        "directivo_por_tipo": cupo_directivo, "directivo_cupo_estandar_por_tipo": 5,
        "directivo_porcentaje_sobre_estandar": cupo_directivo * 20,
        "directivo_cupo_del_escenario_por_tipo": cupo_directivo,
        "cobertura_sobre_cupos_del_escenario": 100,
        "personas_disponibles": len(por_persona), "personas_seleccionadas": len(utilizados),
        "personas_no_seleccionadas": len(por_persona) - len(utilizados),
        "filas_candidaturas": len(detalle), "superior_personas_distintas": 60,
        "superior_candidaturas_por_persona": 3,
        "departamentos_disponibles": disponibles_departamento,
        "departamentales_necesarios_por_departamento": 20,
        "distribucion_personas_por_departamento_principal": dict(sorted(Counter(
            principales[k]["Departamento Principal"] for k in utilizados).items())),
        "presentaciones": presentaciones,
    }
    (SALIDA / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SALIDA / "LEEME.md").write_text(crear_leeme(resumen), encoding="utf-8")
    validar_resultados(por_persona, autoridades, presentaciones, cupo_directivo)
    if hashlib.sha256(padron.read_bytes()).hexdigest() != huella:
        raise ValueError("El padrón de origen cambió durante la generación.")
    print(json.dumps({k: v for k, v in resumen.items() if k != "presentaciones"}, ensure_ascii=True, indent=2))


def validar_resultados(por_persona, autoridades, presentaciones, cupo_directivo):
    apariciones = defaultdict(list)
    superior_por_grupo = {}
    for lista in presentaciones:
        filas = leer_csv(SALIDA / "importacion_completa" / lista["archivo"], ";")
        codigo = lista["codigo_presentacion"].split("-")[2]
        esperados = puestos(codigo, cupo_directivo)
        if len(filas) != sum(cupo * 2 for _, _, _, cupo in esperados):
            raise ValueError("Cantidad incorrecta de candidaturas.")
        personas_lista = set()
        for fila in filas:
            clave = fila["tipo_documento"], fila["documento"]
            if clave in personas_lista or clave in autoridades or clave not in por_persona:
                raise ValueError("Persona repetida en la lista, autoridad o ajena al padrón.")
            personas_lista.add(clave)
            if fila["departamento"] and not any(
                r["Depto/Carrera"] == codigo for r in por_persona[clave]
            ):
                raise ValueError("Candidatura departamental fuera del padrón correspondiente.")
            apariciones[clave].append((lista["numero_lista"], fila["puesto"], fila["tipo_candidatura"], fila["orden"]))
        for _, puesto, alcance, cupo in esperados:
            departamento = DEPARTAMENTOS[alcance][2] if alcance else ""
            for tipo in ("titular", "suplente"):
                ordenes = [int(f["orden"]) for f in filas if
                           (f["puesto"], f["departamento"], f["tipo_candidatura"]) == (puesto, departamento, tipo)]
                if ordenes != list(range(1, cupo + 1)):
                    raise ValueError("Cupo incompleto u orden no consecutivo.")
        superior = [(f["documento"], f["tipo_candidatura"], f["orden"]) for f in filas if f["puesto"] == SUPERIOR]
        if codigo in DEPARTAMENTOS:
            anterior = superior_por_grupo.setdefault(lista["numero_lista"], superior)
            if superior != anterior or len(superior) != 30:
                raise ValueError("Superior difiere entre sublistas de la misma familia.")
        if leer_csv(SALIDA / lista["archivo"], ";") != [{k: f[k] for k in MULTIPUESTO} for f in filas]:
            raise ValueError("Los dos formatos CSV difieren.")
    for referencias in apariciones.values():
        if len(referencias) == 1:
            if referencias[0][1] == SUPERIOR:
                raise ValueError("Superior no se comparte en las tres sublistas.")
        elif len(referencias) != 3 or len(set(referencias)) != 1 or referencias[0][1] != SUPERIOR:
            raise ValueError("Repetición no autorizada entre listas o cargos.")
    if len(apariciones) != 128 + 12 * cupo_directivo:
        raise ValueError("La cantidad de personas distintas no coincide con los cupos.")


def crear_leeme(resumen):
    cupo = resumen["directivo_por_tipo"]
    return f"""# Docentes: dos familias de sublistas y dos listas DASUTeN

Origen: `padron_docentes_sin_autoridades.csv` de segmento_1_500, contrastado con las
autoridades asignadas de la foto de instancia 3. Se cuentan personas por documento,
sin duplicar a quienes tienen registros en dos departamentos: hay 385 personas y 451 registros.

Las familias 19 — 19 de agosto y 2 — Integración tienen tres sublistas cada una:
Sistemas (K), Industrial (I) y Electrónica (R). Son seis presentaciones distintas.
El número 19 o 2 se mantiene dentro de cada familia; el nombre y el código de
presentación distinguen cada sublista. La familia es una agrupación de estos
archivos de prueba; no crea una entidad nueva en la aplicación.

Además hay dos presentaciones, una por familia, exclusivamente para DASUTeN.

| Presentación | Superior T+S | Directivo T+S | Departamental T+S | DASUTeN T+S |
|---|---:|---:|---:|---:|
| Cada una de las seis sublistas departamentales | 15+15 | {cupo}+{cupo} | 5+5 del propio departamento | — |
| Cada una de las dos listas DASUTeN | — | — | — | 2+2 |

El cupo de Directivo de estos casos es {cupo}+{cupo}, confirmado por el usuario.
Todos los cuerpos cubren el 100 % de los cupos de este escenario y superan el mínimo del 50 %.
El estándar documentado del proyecto es 5+5 para Directivo: estos archivos no cambian
los parámetros ni la base. Antes de importarlos, configurar {cupo} titulares y {cupo}
suplentes para Directivo de Docentes y habilitar los demás puestos con los cupos
indicados arriba. Con un cupo de 5+5, estos candidatos de Directivo representarían
el {resumen['directivo_porcentaje_sobre_estandar']} %, por debajo del mínimo solicitado.

Alcanzan los tres departamentos: K dispone de {resumen['departamentos_disponibles']['K']} personas,
I de {resumen['departamentos_disponibles']['I']} y R de {resumen['departamentos_disponibles']['R']}.
Se reservan veinte de cada departamento para completar las dos departamentales.
Los candidatos a Superior, Directivo y DASUTeN pueden pertenecer a cualquier departamento.

Se seleccionan {resumen['personas_seleccionadas']} personas distintas; quedan
{resumen['personas_no_seleccionadas']} sin seleccionar. Los CSV contienen
{resumen['filas_candidaturas']} candidaturas: los mismos quince titulares y quince suplentes
de Superior se repiten, con idéntico orden, en las tres sublistas de su familia.
Las dos familias tienen nóminas diferentes. No hay otras repeticiones entre cargos,
sublistas ni listas DASUTeN. Los apoderados son ocho ejemplos ficticios externos al
padrón, sin candidatura; pueden reemplazarse por los datos reales antes de importar.

## Carga

1. Consultar `listas_y_apoderados.csv` para crear las ocho listas con sus nombres,
   números, códigos y apoderados. Asociar los tres puestos de cada sublista o
   el único puesto de cada lista DASUTeN, según corresponda.
2. Dentro de cada lista, abrir **Importar por CSV (uno o varios puestos)** y elegir
   el archivo `lista_*.csv` correspondiente de esta carpeta.
3. Revisar la previsualización y confirmar. Al cargar las siguientes sublistas de
   una familia, la aplicación puede advertir que Superior figura en otra
   presentación. Esa repetición es intencional y está solicitada para estos casos.

Alternativamente, `importacion_completa/` contiene los mismos ocho CSV con trece
columnas para `/gestion/elecciones/<id>/candidaturas/importar/`: incluyen los datos
de cada presentación y permiten crearla con sus asociaciones. Elegir una sola vía
de carga para cada lista.

Los archivos principales tienen seis columnas:
`puesto;departamento;tipo_documento;documento;tipo_candidatura;orden`.
Se usa UTF-8 con BOM, separador punto y coma y nombre completo de departamento.
Los puestos generales dejan departamento vacío. El orden empieza en 1 para cada
puesto y tipo de candidatura. No se incluye Ciencias Básicas como puesto adicional.

## Revisión

- `detalle_candidatos.csv`: identidades, cargos, departamento principal y registros
  departamentales de origen. Superior aparece tres veces por persona.
- `cobertura.csv`: cantidades y cobertura por puesto de cada presentación.
- `resumen.json`: personas distintas, candidaturas, distribución por departamento
  principal, huellas SHA-256 y metadatos de las ocho listas.

Regenerar con `python scripts/generar_listas_docentes_demo.py --directivo {cupo}`.
El generador comprueba identidad, pertenencia departamental, cupos, órdenes,
exclusión de autoridades y que la única repetición sea Superior dentro de su familia.
No modifica el padrón ni crea candidatos en la base de datos.
"""


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--directivo", type=int, choices=(2, 3, 5), default=2,
                           help="Cupo y candidatos por tipo para Directivo en estos casos (confirmado: 2).")
    generar(argumentos.parse_args().directivo)
