"""Genera CSV ficticios de carga; no consulta ni modifica la base de datos."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


DESTINO = Path(__file__).resolve().parent / "carga_alumnos_20000"
DEPARTAMENTOS = ("K", "I", "R", "O", "S")
PERSONAS_POR_DEPARTAMENTO = 3700
ADICIONALES_POR_DEPARTAMENTO = 300
MAXIMO_POR_MESA = 300
CABECERAS_PADRON = (
    "DNI", "Tipo Documento", "Legajo", "Nombre", "Apellido", "Depto/Carrera", "Mail",
    "TieneDiscapacidad", "Departamento Principal", "Sede donde cursa", "Turno", "Nivel",
)
CABECERAS_NOMINA = ("Tipo documento", "Documento", "Legajo")
NOMBRES = ("Ana", "Bruno", "Camila", "Diego", "Elena", "Facundo", "Gabriela", "Hugo", "Irene", "Joaquin")
APELLIDOS = ("Acosta", "Benitez", "Castro", "Diaz", "Fernandez", "Garcia", "Herrera", "Lopez", "Molina", "Perez", "Ramirez", "Romero", "Ruiz", "Sanchez", "Torres")


def escribir_csv(nombre, cabeceras, filas):
    ruta = DESTINO / nombre
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=cabeceras)
        escritor.writeheader()
        escritor.writerows(filas)
    return ruta


def generar():
    DESTINO.mkdir(parents=True, exist_ok=True)
    principales, adicionales = [], []
    for posicion, departamento in enumerate(DEPARTAMENTOS):
        duplicados = {i * PERSONAS_POR_DEPARTAMENTO // ADICIONALES_POR_DEPARTAMENTO for i in range(ADICIONALES_POR_DEPARTAMENTO)}
        for indice in range(PERSONAS_POR_DEPARTAMENTO):
            numero = posicion * PERSONAS_POR_DEPARTAMENTO + indice + 1
            fila = {
                "DNI": str(70000000 + numero), "Tipo Documento": "DNI", "Legajo": f"P20K{numero:05d}",
                "Nombre": NOMBRES[numero % len(NOMBRES)],
                "Apellido": f"{APELLIDOS[numero % len(APELLIDOS)]} Prueba{numero:05d}",
                "Depto/Carrera": departamento, "Mail": f"prueba.carga20k.{numero:05d}@frba.utn.edu.ar",
                "TieneDiscapacidad": "No", "Departamento Principal": departamento,
                "Sede donde cursa": "", "Turno": "", "Nivel": str(1 + numero % 5),
            }
            principales.append(fila)
            if indice in duplicados:
                adicionales.append({**fila, "Depto/Carrera": DEPARTAMENTOS[(posicion + 1) % len(DEPARTAMENTOS)]})
    filas = principales + adicionales
    frecuencias = Counter(fila["DNI"] for fila in filas)
    assert len(filas) == 20000 and len(frecuencias) == 18500
    assert Counter(frecuencias.values()) == {1: 17000, 2: 1500}
    grupos = defaultdict(list)
    for fila in filas:
        principal = fila["Depto/Carrera"] == fila["Departamento Principal"]
        grupos[(fila["Depto/Carrera"], principal)].append(fila)
    nomina, control_mesas, control_autoridades = [], [], []
    seleccionados = set()
    for (departamento, principal), miembros in sorted(grupos.items()):
        miembros.sort(key=lambda fila: (fila["Apellido"], fila["Nombre"], fila["Legajo"]))
        cantidad_mesas = (len(miembros) + MAXIMO_POR_MESA - 1) // MAXIMO_POR_MESA
        if cantidad_mesas == 1:
            capacidades = [len(miembros)]
        else:
            llenas = cantidad_mesas - 2
            resto = len(miembros) - llenas * MAXIMO_POR_MESA
            capacidades = [MAXIMO_POR_MESA] * llenas + [(resto + 1) // 2, resto // 2]
        inicio = 0
        for numero_mesa, capacidad in enumerate(capacidades, start=1):
            mesa = miembros[inicio:inicio + capacidad]
            inicio += capacidad
            elegibles = [fila for fila in mesa if fila["DNI"] not in seleccionados and (not principal or frecuencias[fila["DNI"]] == 1)]
            assert len(elegibles) >= 9, (departamento, principal, numero_mesa)
            control_mesas.append({
                "Departamento": departamento, "Tipo mesa": "Principal" if principal else "Especial",
                "Mesa dentro del grupo": numero_mesa, "Electores": capacidad,
                "Autoridades Mañana": 3, "Autoridades Tarde": 3, "Autoridades Noche": 3,
            })
            for fila in elegibles[:9]:
                seleccionados.add(fila["DNI"])
                identidad = {"Tipo documento": "DNI", "Documento": fila["DNI"], "Legajo": fila["Legajo"]}
                nomina.append(identidad)
                control_autoridades.append({
                    **identidad, "Nombre": fila["Nombre"], "Apellido": fila["Apellido"],
                    "Departamento referencia": departamento, "Tipo mesa referencia": "Principal" if principal else "Especial",
                    "Mesa dentro del grupo referencia": numero_mesa,
                })
    assert len(control_mesas) == 70 and len(nomina) == len(seleccionados) == 630
    assert Counter(fila["Tipo mesa"] for fila in control_mesas) == {"Principal": 65, "Especial": 5}
    assert Counter(fila["Electores"] for fila in control_mesas) == {300: 60, 200: 10}
    archivos = [
        escribir_csv("padron_alumnos_20000_filas.csv", CABECERAS_PADRON, filas),
        escribir_csv("nomina_autoridades_630.csv", CABECERAS_NOMINA, nomina),
        escribir_csv("control_mesas_esperadas.csv", tuple(control_mesas[0]), control_mesas),
        escribir_csv("control_personas_nomina.csv", tuple(control_autoridades[0]), control_autoridades),
    ]
    for ruta, cantidad in zip(archivos, (20000, 630, 70, 630)):
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            assert sum(1 for _ in csv.DictReader(archivo)) == cantidad
    resumen = {
        "filas_padron": 20000, "personas_distintas": 18500, "registros_adicionales": 1500,
        "departamentos": list(DEPARTAMENTOS), "sede_electoral": "Campus", "maximo_por_mesa": 300,
        "mesas_principales": 65, "mesas_especiales": 5, "mesas_totales": 70,
        "mesas_de_300": 60, "mesas_de_200": 10, "autoridades_distintas": 630,
        "turnos": ["Mañana", "Tarde", "Noche"], "titulares_por_mesa_y_turno": 3,
        "registros_sin_restriccion_de_cursada": 20000,
        "archivos": {ruta.name: {"bytes": ruta.stat().st_size, "sha256": hashlib.sha256(ruta.read_bytes()).hexdigest()} for ruta in archivos},
    }
    (DESTINO / "resumen_archivos.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    generar()
