"""Genera casos locales a partir del padrón existente, sin consultar ni alterar la BD."""

import csv
from pathlib import Path


BASE = Path(__file__).resolve().parent
DESTINO = BASE / "variantes_alumnos"
CABECERAS_AUTORIDADES = ["Tipo documento", "Documento", "Legajo"]


def escribir(nombre, filas, cabeceras):
    ruta = DESTINO / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=cabeceras)
        escritor.writeheader()
        escritor.writerows(filas)
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        assert lector.fieldnames == cabeceras
        assert list(lector) == filas, nombre
    print(f"{nombre}: {len(filas)} filas")


def identidad(fila):
    return {"Tipo documento": fila["Tipo Documento"], "Documento": fila["DNI"], "Legajo": fila["Legajo"]}


def autoridades(nombre, filas):
    escribir(nombre, [identidad(fila) for fila in filas], CABECERAS_AUTORIDADES)


def generar():
    with (BASE / "padron_estudiantes_500.csv").open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        cabeceras = lector.fieldnames
        alumnos = list(lector)
    assert len(alumnos) == 500
    assert len({fila["DNI"] for fila in alumnos}) == 500
    assert len({fila["Legajo"] for fila in alumnos}) == 500
    libres = [f for f in alumnos if not f["Sede donde cursa"] and not f["Turno"]]
    campus = [f for f in alumnos if f["Sede donde cursa"] == "Campus" and f["Turno"] == "Mañana"]
    medrano = [f for f in alumnos if f["Sede donde cursa"] == "Medrano" and f["Turno"] == "Mañana"]
    autoridades("sobre_padron_500/01_sin_restriccion_cursada.csv", libres[:12])
    autoridades("sobre_padron_500/02_cursan_campus_manana.csv", campus[:12])
    autoridades("sobre_padron_500/03_cursan_medrano_manana.csv", medrano[:12])
    autoridades("sobre_padron_500/04_solo_departamento_K.csv", [f for f in libres if f["Depto/Carrera"] == "K"][:12])
    autoridades("sobre_padron_500/05_un_candidato_faltantes.csv", libres[:1])
    autoridades("sobre_padron_500/06_reimportar_mismo_candidato.csv", libres[:1])
    a, b = map(identidad, libres[:2])
    desconocido = {"Tipo documento": "DNI", "Documento": "79999999", "Legajo": "799999"}
    assert desconocido["Documento"] not in {f["DNI"] for f in alumnos}
    assert desconocido["Legajo"] not in {f["Legajo"] for f in alumnos}
    casos = {
        "07_error_no_existe.csv": [desconocido],
        "08_error_duplicado_exacto.csv": [a, a],
        "09_error_documento_legajo_cruzados.csv": [{**a, "Legajo": b["Legajo"]}],
        "10_error_sin_identificadores.csv": [{"Tipo documento": "DNI", "Documento": "", "Legajo": ""}],
        "11_error_lote_mixto_atomico.csv": [a, desconocido, b],
        "12_valido_solo_documento.csv": [{**a, "Legajo": ""}],
        "13_valido_solo_legajo.csv": [{**a, "Documento": ""}],
        "14_error_tipo_documento_incorrecto.csv": [{**a, "Tipo documento": "CUIL"}],
        "15_repetido_identificadores_alternativos.csv": [{**a, "Legajo": ""}, {**a, "Documento": ""}],
    }
    for nombre, filas in casos.items():
        escribir("sobre_padron_500/" + nombre, filas, CABECERAS_AUTORIDADES)

    # Mismas identidades locales; variantes alternativas, nunca padrones acumulativos.
    muestra = [dict(f) for f in libres if f["Depto/Carrera"] == "K"][:12]
    assert len(muestra) == 12
    for indice, fila in enumerate(muestra):
        fila["Nivel"] = "1" if indice < 6 else "2"
    escribir("controlados/01_padron_12_sin_cursada.csv", muestra, cabeceras)
    con_cursada = [{**f, "Sede donde cursa": "Campus", "Turno": "Mañana"} for f in muestra]
    escribir("controlados/02_padron_12_cursan_campus_manana.csv", con_cursada, cabeceras)
    autoridades("controlados/03_autoridades_12.csv", muestra)
    autoridades("controlados/04_autoridades_3_reparto.csv", muestra[:3])
    autoridades("controlados/05_autoridades_1_faltantes.csv", muestra[:1])
    autoridades("controlados/06_autoridades_6_nivel_1_cambio_sede.csv", muestra[:6])
    for nombre, cambio in (
        ("07_error_padron_sede_sin_turno.csv", {"Sede donde cursa": "Campus", "Turno": ""}),
        ("08_error_padron_turno_inexistente.csv", {"Sede donde cursa": "Campus", "Turno": "TURNO_INEXISTENTE_PRUEBA"}),
        ("09_error_padron_sede_inexistente.csv", {"Sede donde cursa": "SEDE_INEXISTENTE_PRUEBA", "Turno": "Mañana"}),
    ):
        escribir("controlados/" + nombre, [{**muestra[0], **cambio}], cabeceras)
    escribir("controlados/10_error_padron_sin_columna_turno.csv",
             [{k: v for k, v in con_cursada[0].items() if k != "Turno"}],
             [c for c in cabeceras if c != "Turno"])
    escribir("controlados/11_padron_1_origen_no_movible.csv", muestra[:1], cabeceras)
    escribir("controlados/12_padron_13_origen_no_movible.csv",
             muestra + [{**next(f for f in libres if f["Depto/Carrera"] == "K" and f["DNI"] not in {r["DNI"] for r in muestra}), "Nivel": "3"}], cabeceras)
    with (DESTINO / "controlados/12_padron_13_origen_no_movible.csv").open(encoding="utf-8-sig", newline="") as archivo:
        trece = list(csv.DictReader(archivo))
    autoridades("controlados/13_autoridad_unica_nivel_3.csv", trece[-1:])


if __name__ == "__main__":
    generar()
