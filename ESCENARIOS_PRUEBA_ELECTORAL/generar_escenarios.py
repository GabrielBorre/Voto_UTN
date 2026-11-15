"""Generación offline reproducible. Solo biblioteca estándar de Python 3.12."""
import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CLAUSTROS = ('estudiantes', 'docentes', 'graduados', 'no_docentes')
CABECERAS = ('DNI', 'Tipo Documento', 'Legajo', 'Nombre', 'Apellido', 'Depto/Carrera', 'Mail',
             'TieneDiscapacidad', 'Departamento Principal', 'Sede donde cursa', 'Turno', 'Nivel')
NOMBRES = ('Carlos', 'Lucía', 'Martín', 'Ana', 'Sofía', 'Diego', 'Valentina', 'Joaquín',
           'Camila', 'Tomás', 'María', 'Nicolás', 'Julieta', 'Santiago', 'Paula', 'Gabriel',
           'Agustina', 'Federico', 'Florencia', 'Matías', 'Elena', 'Andrés', 'Carolina', 'Iván',
           'Victoria', 'Bruno', 'Natalia', 'Emilia', 'Pablo', 'Daniela')
APELLIDOS = ('Gómez', 'Fernández', 'Rodríguez', 'González', 'López', 'Martínez', 'Pérez',
             'García', 'Sánchez', 'Romero', 'Díaz', 'Torres', 'Álvarez', 'Ruiz', 'Acosta',
             'Benítez', 'Medina', 'Herrera', 'Suárez', 'Castro', 'Molina', 'Núñez', 'Muñoz',
             'Ríos', 'Silva', 'Vega', 'Cabrera', 'Morales', 'Domínguez', 'Peralta')


def huella(valor):
    return hashlib.sha256(json.dumps(valor, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def leer_configuracion(raiz=RAIZ):
    bloques = re.findall(r'^```json\s*\n(.*?)^```', (raiz / 'DECISIONES.md').read_text(encoding='utf-8'), re.M | re.S)
    if len(bloques) != 1:
        raise ValueError('DECISIONES.md debe tener exactamente un bloque json.')
    c = json.loads(bloques[0])
    if c['version'] != 1 or type(c['semilla']) is not int or not 0 <= c['semilla'] < 10000:
        raise ValueError('Versión no compatible o semilla fuera de 0..9999.')
    for clave in ('departamentos', 'secundarios'):
        if not c[clave] or any(type(v) not in (int, float) or v <= 0 for v in c[clave].values()) or not math.isclose(sum(c[clave].values()), 100):
            raise ValueError(f'{clave}: pesos positivos que sumen 100.')
    if set(c['departamentos']) != set('KIR SOVQUW'.replace(' ', '')) or not set(c['secundarios']) <= set(c['departamentos']):
        raise ValueError('Revisá los códigos de departamentos.')
    for cl, pesos in c.get('distribucion_por_claustro', {}).items():
        if cl not in CLAUSTROS[:3] or (pesos and (set(pesos) != set(c['departamentos']) or
                any(type(v) not in (int, float) or v <= 0 for v in pesos.values()) or not math.isclose(sum(pesos.values()), 100))):
            raise ValueError('Cada distribución por claustro debe tener nueve porcentajes positivos que sumen 100.')
    if any(not 0 <= v <= 100 for v in c.get('porcentaje_medrano', {}).values()):
        raise ValueError('El porcentaje por sede debe estar entre 0 y 100.')
    if len(c['sedes']) != 2 or set(c['sedes']) != {'Campus', 'Medrano'} or len(c['turnos']) != 3 or len(set(c['turnos'])) != 3:
        raise ValueError('Se requieren Campus, Medrano y tres turnos distintos.')
    if not 0 <= c['docentes_basicas_porcentaje'] <= 100:
        raise ValueError('Porcentaje de Ciencias Básicas inválido.')
    for cl in CLAUSTROS:
        if type(c['maximo_mesa'][cl]) is not int or c['maximo_mesa'][cl] < 1 or not 0 <= c['actividad_porcentaje'][cl] <= 100:
            raise ValueError(f'Capacidad o actividad inválida: {cl}.')
    if c['actividad_porcentaje']['no_docentes'] != 100 or c['actividad_porcentaje']['graduados'] != 0:
        raise ValueError('Acuerdo vigente: no docentes 100% de actividad y graduados 0%.')
    a = c['autoridades']
    if not 2 <= a['minimo'] < a['maximo'] <= 3 or a['manuales'] < 0 or a['nomina_pequena'] < 0:
        raise ValueError('Se requieren dos a tres autoridades y cantidades no negativas.')
    nombres = set()
    if len(c['segmentos']) != 3:
        raise ValueError('Se requieren tres segmentos.')
    for s in c['segmentos']:
        nombre = s['carpeta']
        if not re.fullmatch(r'segmento_[a-zA-Z0-9_]+', nombre) or nombre in nombres:
            raise ValueError('Carpeta de segmento inválida o repetida.')
        nombres.add(nombre)
        for cl in CLAUSTROS:
            n = s['personas'][cl]
            if type(n) is not int or not 1 <= n <= 9000:
                raise ValueError('Personas debe estar entre 1 y 9000.')
            ad = s['adicionales'].get(cl, 0)
            if type(ad) is not int or not 0 <= ad < n or (cl in ('graduados', 'no_docentes') and ad):
                raise ValueError('Cantidad de secundarios inválida.')
        if s['solicitudes'] < 1 or s['justificativos'] < 1:
            raise ValueError('Se requieren solicitudes y justificativos positivos.')
    return c


def repartir(total, pesos):
    valores = {k: total * v / sum(pesos.values()) for k, v in pesos.items()}
    cantidades = {k: int(v) for k, v in valores.items()}
    for k in sorted(valores, key=lambda k: (-(valores[k] - cantidades[k]), k))[:total - sum(cantidades.values())]:
        cantidades[k] += 1
    return cantidades


def capacidades(n, maximo):
    mesas = math.ceil(n / maximo)
    if mesas <= 1:
        return [n] if n else []
    llenas = mesas - 2
    resto = n - llenas * maximo
    return [maximo] * llenas + [(resto + 1) // 2, resto // 2]


def texto_csv(filas, campos):
    salida = io.StringIO(newline='')
    escritor = csv.DictWriter(salida, fieldnames=campos)
    escritor.writeheader()
    escritor.writerows(filas)
    return salida.getvalue().encode('utf-8-sig')


def nomina_con_movilidad(opciones, mesas, autoridades, personas, reservados):
    """Desequilibra únicamente la nómina, conservando cantidad e identidades válidas."""
    cantidad = opciones['reemplazos']
    if type(cantidad) is not int or cantidad < 1:
        raise ValueError('Los reemplazos de nómina deben ser enteros positivos.')
    usados = {a['Documento'] for a in autoridades}
    principales = {p['DNI']: p for p in personas}
    # Las personas sin secundarios solo aparecen en una mesa: no se agrega una vía alternativa por otro departamento.
    apariciones = defaultdict(int)
    for mesa in mesas:
        for dni in mesa['personas']:
            apariciones[dni] += 1
    candidatas = []
    for mesa in mesas:
        if mesa['departamento'] != opciones['departamento'] or mesa['sede'] != opciones['sede'] or mesa['especial']:
            continue
        removibles = [a for a in autoridades if a['departamento'] == mesa['departamento'] and a['sede'] == mesa['sede']
                      and not a['especial'] and a['ordinal'] == mesa['ordinal']]
        donantes = []
        for otra in mesas:
            if otra is mesa or otra['especial'] or otra['departamento'] != mesa['departamento'] or otra['sede'] != opciones.get('sede_donantes', mesa['sede']):
                continue
            for dni in otra['personas']:
                if dni not in usados | reservados and apariciones[dni] == 1 and not principales[dni]['Sede donde cursa']:
                    donantes.append((dni, otra['ordinal']))
        if len(removibles) >= cantidad and len(donantes) >= cantidad:
            candidatas.append((mesa, removibles, sorted(donantes)))
    if not candidatas:
        raise ValueError('La nómina de movilidad no tiene suficientes candidatos de otras mesas compatibles.')
    mesa, removibles, donantes = candidatas[0]
    quitados = removibles[:cantidad]
    documentos_quitados = {a['Documento'] for a in quitados}
    agregados = [{'Tipo documento': 'DNI', 'Documento': dni, 'Legajo': principales[dni]['Legajo']} for dni, _ in donantes[:cantidad]]
    resultado = [a for a in autoridades if a['Documento'] not in documentos_quitados] + agregados
    detalle = {'mesa_con_deficit': {k: v for k, v in mesa.items() if k != 'personas'},
               'quitados': sorted(documentos_quitados),
               'sede_donantes': opciones.get('sede_donantes', mesa['sede']),
               'agregados': [{'dni': dni, 'mesa_origen_ordinal': ordinal, 'nombre': principales[dni]['Nombre'],
                             'apellido': principales[dni]['Apellido']} for dni, ordinal in donantes[:cantidad]]}
    return resultado, detalle


def construir(c, s):
    archivos, control = {}, {'configuracion': c, 'huella_configuracion': huella(c), 'segmento': s,
                             'claustros': {}, 'solicitudes': [], 'manuales': [], 'nomina_pequena': []}
    for ci, cl in enumerate(CLAUSTROS):
        n = s['personas'][cl]
        pesos = (c.get('distribucion_por_claustro', {}).get(cl) or c['departamentos']).copy()
        if cl == 'docentes':
            pesos = {k: v * (100 - c['docentes_basicas_porcentaje']) / 100 for k, v in pesos.items()}
            pesos['Z'] = c['docentes_basicas_porcentaje']
        if cl == 'no_docentes':
            pesos = {'': 100}
        personas, adicionales = [], []
        por_depto = {}
        for depto, cantidad in repartir(n, pesos).items():
            grupo = []
            for i in range(cantidad):
                indice = ci * 100000 + ('KIR SOVQUWZ'.replace(' ', '').index(depto) if depto else 0) * 9000 + i + 1
                dni = str(10000000 + c['semilla'] * 1000000 + indice)
                azar = random.Random(f'{c["semilla"]}:{indice}')
                fila = dict(zip(CABECERAS, (dni, 'DNI', dni, azar.choice(NOMBRES), azar.choice(APELLIDOS), depto,
                           f'escenario.{dni}@frba.utn.edu.ar', 'No', depto, '', '', '1')))
                grupo.append(fila)
            por_depto[depto] = grupo
            personas.extend(grupo)
        carlos = por_depto.get('K', [None])[0] if cl == 'estudiantes' else None
        if carlos:
            carlos.update({'DNI': '38999222', 'Legajo': '4444443', 'Nombre': 'Carlos', 'Apellido': 'Gomez',
                           'Mail': 'alumnocg@frba.utn.edu.ar'})
        # Reservar solicitantes de Sistemas y los secundarios antes de repartir actividad.
        solicitudes = por_depto['K'][1:s['solicitudes'] + 1] if cl == 'estudiantes' else []
        if cl == 'estudiantes' and len(solicitudes) != s['solicitudes']:
            raise ValueError('Sistemas no alcanza para reservar solicitantes.')
        reservados = {f['DNI'] for f in solicitudes + ([carlos] if carlos else [])}
        dobles = set()
        for destino, cantidad in repartir(s['adicionales'].get(cl, 0), c['secundarios']).items():
            candidatos = [f for f in personas if f['Depto/Carrera'] != destino and f['DNI'] not in dobles | reservados]
            # Concentrar en departamentos grandes y alternar sedes dentro del grupo adicional.
            candidatos.sort(key=lambda f: (0 if f['Depto/Carrera'] in ('K', 'I') else 1, f['DNI']))
            if len(candidatos) < cantidad:
                raise ValueError('No hay personas suficientes para secundarios.')
            for f in candidatos[:cantidad]:
                dobles.add(f['DNI'])
                adicionales.append({**f, 'Depto/Carrera': destino})
        inactivos = reservados | dobles
        cantidad_actividad = repartir(n, {'si': c['actividad_porcentaje'][cl], 'no': 100 - c['actividad_porcentaje'][cl]})['si']
        elegibles = [f for f in personas if f['DNI'] not in inactivos]
        if len(elegibles) < cantidad_actividad:
            raise ValueError(f'{cl}: actividad incompatible con secundarios y reservas sin actividad.')
        # Intercalar departamentos para no concentrar actividad en uno solo.
        elegibles.sort(key=lambda f: hashlib.sha256(f['DNI'].encode()).hexdigest())
        activos = {f['DNI'] for f in elegibles[:cantidad_actividad]}
        sedes = {}
        for depto, grupo in por_depto.items():
            mitad = int(len(grupo) * c.get('porcentaje_medrano', {}).get(cl, 50) / 100)
            if cl == 'estudiantes':
                if depto == 'K':
                    mitad = max(c['maximo_mesa'][cl], (mitad // c['maximo_mesa'][cl]) * c['maximo_mesa'][cl])
                if len(grupo) < 2 * len(c['turnos']) * c['autoridades']['maximo']:
                    mitad = 0
            # Reservados al principio en Campus; Medrano desde el final.
            for i, f in enumerate(grupo):
                sede = 'Medrano' if i >= len(grupo) - mitad else 'Campus'
                if cl == 'estudiantes':
                    sede = c['sede_unica_estudiantes'].get(depto, sede)
                if cl in c['sede_electoral']:
                    sede_voto = c['sede_electoral'][cl]
                else:
                    sede_voto = sede
                sedes[f['DNI']] = sede_voto
                f['Nivel'] = str(4 + i % 2 if sede_voto == 'Medrano' else 1 + i % 3)
                if f['DNI'] in activos:
                    f['Sede donde cursa'] = sede
                    f['Turno'] = c['turnos'][i % 3]
        por_dni = {f['DNI']: f for f in personas}
        adicionales = [{**por_dni[f['DNI']], 'Depto/Carrera': f['Depto/Carrera']} for f in adicionales]
        filas = personas + adicionales
        grupos = defaultdict(list)
        for f in filas:
            grupos[(f['Depto/Carrera'], sedes[f['DNI']], f['Depto/Carrera'] != f['Departamento Principal'])].append(f)
        mesas = []
        for (depto, sede, especial), grupo in sorted(grupos.items()):
            grupo.sort(key=lambda f: (f['Apellido'], f['Nombre'], f['Legajo']))
            inicio = 0
            for numero, tamano in enumerate(capacidades(len(grupo), c['maximo_mesa'][cl]), 1):
                miembros = grupo[inicio:inicio + tamano]
                inicio += tamano
                mesas.append({'departamento': depto, 'sede': sede, 'especial': especial, 'ordinal': numero,
                              'personas': [f['DNI'] for f in miembros]})
        # Emparejar plazas y personas en toda la elección del claustro, incluidas mesas especiales.
        opciones, plazas = {}, []
        for mi, mesa in enumerate(mesas):
            for turno in c['turnos']:
                candidatos = [dni for dni in mesa['personas'] if dni not in reservados and por_dni[dni]['Turno'] != turno]
                for orden in range(c['autoridades']['maximo']):
                    plaza = (mi, turno, orden)
                    opciones[plaza] = candidatos
                    plazas.append(plaza)
        persona_plaza = {}

        def asignar(plaza, vistos):
            for dni in opciones[plaza]:
                if dni in vistos:
                    continue
                vistos.add(dni)
                if dni not in persona_plaza or asignar(persona_plaza[dni], vistos):
                    persona_plaza[dni] = plaza
                    return True
            return False

        obligatorias = [p for p in plazas if p[2] < c['autoridades']['minimo']]
        opcionales = [p for p in plazas if p not in obligatorias]
        for plaza in sorted(obligatorias, key=lambda p: len(opciones[p])):
            if not asignar(plaza, set()):
                raise ValueError(f'{cl}: no alcanza para cubrir tres turnos de {mesas[plaza[0]]}. Ajustá distribución/capacidad.')
        for plaza in sorted(opcionales, key=lambda p: len(opciones[p])):
            asignar(plaza, set())
        autoridades = [{'Documento': dni, 'Legajo': por_dni[dni]['Legajo'], 'Tipo documento': 'DNI',
                        'turno': plaza[1], **{k: v for k, v in mesas[plaza[0]].items() if k != 'personas'}}
                       for dni, plaza in sorted(persona_plaza.items(), key=lambda item: item[1])]
        archivos[f'padron_{cl}.csv'] = texto_csv(filas, CABECERAS)
        campos_nomina = ('Tipo documento', 'Documento', 'Legajo')
        archivos[f'nomina_{cl}.csv'] = texto_csv([{k: a[k] for k in campos_nomina} for a in autoridades], campos_nomina)
        control['claustros'][cl] = {'personas': n, 'filas': len(filas), 'adicionales': len(adicionales),
                                   'actividad': cantidad_actividad, 'mesas': mesas, 'autoridades_referencia': autoridades,
                                   'sedes_por_persona': sedes}
        if cl == 'estudiantes':
            control['solicitudes'] = [{'dni': f['DNI'], 'origen': sedes[f['DNI']], 'destino': 'Medrano'} for f in solicitudes]
            if any(f['origen'] == f['destino'] for f in control['solicitudes']) or sedes[carlos['DNI']] != 'Campus':
                raise ValueError('Las reservas de Sistemas deben comenzar en Campus.')
            a = c['autoridades']
            control['manuales'] = autoridades[:a['manuales']]
            pequena = autoridades[a['manuales']:a['manuales'] + a['nomina_pequena']]
            if len(pequena) != a['nomina_pequena']:
                raise ValueError('No alcanza la nómina de demostración.')
            opciones_movilidad = c.get('nomina_movilidad', {}).get(s['carpeta'])
            if opciones_movilidad:
                movilidad, detalle = nomina_con_movilidad(opciones_movilidad, mesas, autoridades, personas, reservados)
                archivos['nomina_estudiantes_movilidad.csv'] = texto_csv([{k: a[k] for k in campos_nomina} for a in movilidad], campos_nomina)
                control['nomina_movilidad'] = detalle
            ampliacion = c.get('ampliacion_cambios', {}).get(s['carpeta'])
            if ampliacion:
                cantidad = ampliacion['cantidad']
                if type(cantidad) is not int or cantidad < 1 or ampliacion['origen'] == ampliacion['destino']:
                    raise ValueError('Revisá la cantidad y las sedes de la ampliación de solicitudes.')
                adicionales_compatibles = {f['DNI'] for f in adicionales if f['Depto/Carrera'] == ampliacion['departamento_adicional']}
                candidatos = sorted((f for f in personas if f['DNI'] in adicionales_compatibles
                    and f['DNI'] not in reservados and f['Depto/Carrera'] == ampliacion['departamento_principal']
                    and not f['Sede donde cursa'] and sedes[f['DNI']] == ampliacion['origen']), key=lambda f: f['DNI'])
                if len(candidatos) < cantidad:
                    raise ValueError('No hay suficientes personas sin actividad con esos departamentos para ampliar solicitudes.')
                control['ampliacion_solicitudes'] = [{'dni': f['DNI'], 'origen': ampliacion['origen'],
                    'destino': ampliacion['destino']} for f in candidatos[:cantidad]]
                cantidad_compartida = ampliacion.get('solicitantes_nomina_pequena', 0)
                if type(cantidad_compartida) is not int or not 0 <= cantidad_compartida <= len(pequena):
                    raise ValueError('La cantidad de solicitantes en la nómina pequeña es inválida.')
                documentos_solicitantes = {f['dni'] for f in control['ampliacion_solicitudes']}
                documentos_manuales = {f['Documento'] for f in control['manuales']}
                compartidos = [f for f in autoridades if f['Documento'] in documentos_solicitantes
                               and f['Documento'] not in documentos_manuales][:cantidad_compartida]
                if len(compartidos) != cantidad_compartida:
                    raise ValueError('No hay suficientes solicitantes en la nómina completa para la demostración.')
                restantes = [f for f in pequena if f['Documento'] not in documentos_solicitantes]
                pequena = compartidos + restantes[:a['nomina_pequena'] - cantidad_compartida]
                if len(pequena) != a['nomina_pequena']:
                    raise ValueError('No alcanza la nómina pequeña al incluir a los solicitantes.')
                control['solicitantes_nomina_pequena'] = [f['Documento'] for f in compartidos]
            control['nomina_pequena'] = pequena
            archivos['nomina_estudiantes_pequena.csv'] = texto_csv([{k: f[k] for k in campos_nomina} for f in pequena], campos_nomina)
    control['archivos'] = {nombre: hashlib.sha256(datos).hexdigest() for nombre, datos in archivos.items()}
    archivos['control.json'] = (json.dumps(control, ensure_ascii=False, indent=2) + '\n').encode()
    return archivos


def generar(raiz=RAIZ):
    c = leer_configuracion(raiz)
    # Construir todo antes de archivar o tocar las salidas vigentes.
    versiones = {s['carpeta']: construir(c, s) for s in c['segmentos']}
    with tempfile.TemporaryDirectory(prefix='escenarios-') as temporal:
        tmp = Path(temporal)
        for nombre, archivos in versiones.items():
            (tmp / nombre).mkdir()
            for archivo, datos in archivos.items():
                (tmp / nombre / archivo).write_bytes(datos)
        anteriores = list(raiz.glob('segmento_*'))
        if anteriores:
            archivo = raiz / 'historicos' / datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
            archivo.mkdir(parents=True)
            for ruta in raiz.iterdir():
                if ruta.is_file() and ruta.suffix in ('.md', '.py', '.json'):
                    shutil.copy2(ruta, archivo / ruta.name)
            # Recuperar scripts/documentos efectivos previos, no los recién editados.
            efectivo = raiz / 'VERSION_GENERADA.json'
            if efectivo.exists():
                for nombre, contenido in json.loads(efectivo.read_text(encoding='utf-8')).items():
                    (archivo / nombre).write_text(contenido, encoding='utf-8')
            for ruta in anteriores:
                if ruta.is_dir():
                    shutil.copytree(ruta, archivo / ruta.name)
        for nombre in versiones:
            destino = raiz / nombre
            destino.mkdir(exist_ok=True)
            for ruta in (tmp / nombre).iterdir():
                shutil.copy2(ruta, destino / ruta.name)
        (raiz / 'historicos').mkdir(exist_ok=True)
        (raiz / 'historicos' / '.gitkeep').touch()
        (raiz / 'DECISIONES_GENERACION.md').write_text((raiz / 'DECISIONES.md').read_text(encoding='utf-8'), encoding='utf-8')
        fuentes = {p.name: p.read_text(encoding='utf-8') for p in raiz.iterdir() if p.suffix in ('.py', '.md') and p.is_file()}
        (raiz / 'VERSION_GENERADA.json').write_text(json.dumps(fuentes, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Generados y validados: ' + ', '.join(versiones))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    generar()
