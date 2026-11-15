"""Pruebas offline: ejecutar python -m unittest test_generador.py desde esta carpeta."""
import copy
import csv
import io
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from generar_escenarios import RAIZ, construir, generar, leer_configuracion
from ejecutar_escenario import preparar


class GeneradorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = leer_configuracion()

    def test_conteos_reproduccion_y_personas_reales(self):
        for s in self.c['segmentos']:
            with self.subTest(segmento=s['carpeta']):
                archivos = construir(self.c, s)
                self.assertEqual(archivos, construir(self.c, s))
                control = json.loads(archivos['control.json'])
                for cl, n in s['personas'].items():
                    filas = list(csv.DictReader(io.StringIO(archivos[f'padron_{cl}.csv'].decode('utf-8-sig'))))
                    frecuencias = Counter(f['DNI'] for f in filas)
                    self.assertEqual(len(frecuencias), n)
                    self.assertEqual(len(filas), n + s['adicionales'].get(cl, 0))
                    self.assertLessEqual(max(frecuencias.values()), 2)
                    self.assertTrue(all(f['Nombre'].isalpha() and f['Apellido'].isalpha() for f in filas))
                    self.assertEqual(sum(bool(f['Sede donde cursa']) for f in filas if f['Depto/Carrera'] == f['Departamento Principal']), control['claustros'][cl]['actividad'])
                    aa = control['claustros'][cl]['autoridades_referencia']
                    self.assertEqual(len(aa), len({a['Documento'] for a in aa}))
                self.assertEqual(len(control['solicitudes']), s['solicitudes'])
                self.assertNotIn('38999222', {r['dni'] for r in control['solicitudes']})

    def test_semilla_cambia_personas_y_no_carlos(self):
        otra = copy.deepcopy(self.c)
        otra['semilla'] += 1
        a = construir(self.c, self.c['segmentos'][0])
        b = construir(otra, otra['segmentos'][0])
        self.assertNotEqual(a['padron_estudiantes.csv'], b['padron_estudiantes.csv'])
        self.assertIn(b'38999222', b['padron_estudiantes.csv'])

    def test_nomina_movilidad_conserva_padron_y_cambia_solo_cuatro_personas(self):
        c = copy.deepcopy(self.c)
        c.pop('nomina_movilidad')
        original = construir(c, c['segmentos'][0])
        nuevo = construir(self.c, self.c['segmentos'][0])
        for nombre, contenido in original.items():
            if nombre.endswith('.csv'):
                self.assertEqual(contenido, nuevo[nombre])
        leer = lambda nombre: {r['Documento'] for r in csv.DictReader(io.StringIO(nuevo[nombre].decode('utf-8-sig')))}
        normales = leer('nomina_estudiantes.csv')
        moviles = leer('nomina_estudiantes_movilidad.csv')
        self.assertEqual(len(normales), len(moviles))
        self.assertEqual(len(normales - moviles), 4)
        self.assertEqual(len(moviles - normales), 4)

    def test_segmento_tres_reutiliza_los_otros_claustros(self):
        dos = construir(self.c, self.c['segmentos'][1])
        tres = construir(self.c, self.c['segmentos'][2])
        for cl in ('docentes', 'graduados', 'no_docentes'):
            self.assertEqual(dos[f'padron_{cl}.csv'], tres[f'padron_{cl}.csv'])

    def test_distribucion_independiente_por_claustro(self):
        c = copy.deepcopy(self.c)
        c['distribucion_por_claustro']['graduados'] = {**c['departamentos'], 'K': 35, 'I': 30}
        original = construir(self.c, self.c['segmentos'][0])
        cambiado = construir(c, c['segmentos'][0])
        for cl in ('estudiantes', 'docentes', 'no_docentes'):
            self.assertEqual(original[f'padron_{cl}.csv'], cambiado[f'padron_{cl}.csv'])
        filas = list(csv.DictReader(io.StringIO(cambiado['padron_graduados.csv'].decode('utf-8-sig'))))
        self.assertEqual(Counter(f['Depto/Carrera'] for f in filas)['K'], 175)
        self.assertEqual(Counter(f['Depto/Carrera'] for f in filas)['I'], 150)

    def test_nuevas_mesas_previstas_y_reservas_compatibles(self):
        for s in self.c['segmentos']:
            control = json.loads(construir(self.c, s)['control.json'])
            estudiantes = control['claustros']['estudiantes']
            reservados = {r['dni'] for r in control['solicitudes']} | {'38999222'}
            self.assertFalse(reservados & {a['Documento'] for a in estudiantes['autoridades_referencia']})
            manuales = {a['Documento'] for a in control['manuales']}
            pequena = {a['Documento'] for a in control['nomina_pequena']}
            self.assertFalse(manuales & pequena)
            self.assertEqual(len(manuales), self.c['autoridades']['manuales'])
            self.assertEqual(len(pequena), self.c['autoridades']['nomina_pequena'])
            self.assertTrue(all(r['origen'] != r['destino'] for r in control['solicitudes']))

    def test_archivo_antiguo_y_rechazo_de_alteraciones(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            for p in RAIZ.iterdir():
                if p.is_file() and p.suffix in ('.py', '.md'):
                    shutil.copy2(p, raiz / p.name)
            generar(raiz)
            s = self.c['segmentos'][0]['carpeta']
            preparar(s, 'verificar', 1, raiz=raiz)
            original = (raiz / s / 'padron_estudiantes.csv').read_bytes()
            (raiz / 'generar_escenarios.py').write_text('# versión nueva', encoding='utf-8')
            generar(raiz)
            historial = next(p for p in (raiz / 'historicos').iterdir() if p.is_dir())
            self.assertEqual((historial / s / 'padron_estudiantes.csv').read_bytes(), original)
            self.assertNotEqual((historial / 'generar_escenarios.py').read_text(encoding='utf-8'), '# versión nueva')
            (raiz / s / 'padron_estudiantes.csv').write_bytes(b'alterado')
            with self.assertRaisesRegex(ValueError, 'alterado'):
                preparar(s, 'verificar', 1, raiz=raiz)

    def test_error_no_reemplaza_archivos(self):
        with tempfile.TemporaryDirectory() as directorio:
            raiz = Path(directorio)
            contenido = (RAIZ / 'DECISIONES.md').read_text(encoding='utf-8')
            (raiz / 'DECISIONES.md').write_text(contenido, encoding='utf-8')
            generar(raiz)
            p = raiz / self.c['segmentos'][0]['carpeta'] / 'control.json'
            antes = p.read_bytes()
            (raiz / 'DECISIONES.md').write_text(contenido.replace('"K": 40', '"K": 41'), encoding='utf-8')
            with self.assertRaises(ValueError):
                generar(raiz)
            self.assertEqual(p.read_bytes(), antes)


if __name__ == '__main__':
    unittest.main()
