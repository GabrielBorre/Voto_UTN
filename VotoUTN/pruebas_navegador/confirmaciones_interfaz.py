"""Regresión del diálogo compartido, sin conexión a la app ni escritura en su base.

Requiere Playwright y Chromium instalados para desarrollo.
Ejecutar: python pruebas_navegador/confirmaciones_interfaz.py
"""
import os
import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

PROYECTO = Path(os.environ.get('VOTO_UTN_PROYECTO', Path(__file__).resolve().parents[1]))
BASE = Path(os.environ.get('VOTO_UTN_BASE_PRUEBAS', PROYECTO / 'templates/gestion/base.html'))


class ConfirmacionesInterfazTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.navegador = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.playwright.stop()

    def setUp(self):
        self.pagina = self.navegador.new_page()
        self.envios = []
        self.modulos = set()
        self.errores = []
        self.pagina.on('pageerror', lambda error: self.errores.append(str(error)))
        self.pagina.route('**/*', self.responder)
        self.pagina.goto('http://prueba.local/solicitudes/')
        self.pagina.wait_for_load_state('networkidle')

    def tearDown(self):
        self.pagina.close()

    def responder(self, ruta):
        peticion = ruta.request
        url = urlsplit(peticion.url)
        if peticion.method == 'POST':
            self.envios.append(parse_qs(peticion.post_data or ''))
            ruta.fulfill(content_type='text/html', body='<h1>Envío recibido</h1>')
        elif url.path.startswith('/static/'):
            archivo = (PROYECTO / 'static' / url.path.removeprefix('/static/')).resolve()
            assert archivo.is_relative_to((PROYECTO / 'static').resolve())
            self.modulos.add(url.path + ('?' + url.query if url.query else ''))
            ruta.fulfill(content_type='text/javascript', body=archivo.read_text(encoding='utf-8'))
        else:
            # Usar la URL real de la plantilla base y el módulo consumidor real.
            base = BASE.read_text(encoding='utf-8')
            etiqueta = next(linea for linea in base.splitlines() if 'js/interfaz.js' in linea)
            etiqueta = re.sub(r"\{% static '([^']+)' %\}", r'/static/\1', etiqueta)
            html = '''<!doctype html><html lang="es"><head><meta charset="utf-8">ETIQUETA</head><body>
              <form method="post" data-confirm="Se agrega una mesa. ¿Continuar?">
                <input type="hidden" name="accion" value="aprobar_todas">
                <button>Aceptar todas</button>
              </form>
              <form method="post" data-confirm="¿Rechazar todas?">
                <input type="hidden" name="accion" value="rechazar_todas">
                <button>Rechazar todas</button>
              </form>
              <form method="post" id="formulario-aprobar-con-limite-mesas">
                <input type="hidden" name="accion" value="aprobar_con_maximo_mesas">
                <input type="hidden" name="maximo_mesas_nuevas" id="maximo_mesas_nuevas">
                <button type="button" id="abrir-dialogo-limite-mesas">Aceptar con límite</button>
              </form>
              <dialog id="dialogo-limite-mesas">
                <form method="dialog" id="formulario-dialogo-limite-mesas">
                  <input type="number" required min="0" step="1" id="cantidad-maxima-mesas-nuevas">
                  <button type="button" id="cancelar-dialogo-limite-mesas">Cancelar límite</button>
                  <button>Continuar</button>
                </form>
              </dialog>
              <script type="module" src="/static/js/solicitudes-cambio-sede.js"></script>
              </body></html>'''.replace('ETIQUETA', etiqueta)
            ruta.fulfill(content_type='text/html', body=html)

    def confirmar(self, boton):
        self.pagina.get_by_role('button', name=boton, exact=True).click()
        self.pagina.locator('dialog.utn-dialogo[open]').get_by_role('button', name='Confirmar', exact=True).click()
        self.pagina.wait_for_timeout(400)

    def test_aceptar_todas_envia_una_sola_vez(self):
        self.confirmar('Aceptar todas')
        self.assertEqual(self.envios, [{'accion': ['aprobar_todas']}])
        self.assertFalse(self.errores, self.errores)

    def test_cancelar_no_envia_y_permite_reintentar(self):
        self.pagina.get_by_role('button', name='Aceptar todas', exact=True).click()
        self.pagina.locator('dialog.utn-dialogo[open]').get_by_role('button', name='Cancelar', exact=True).click()
        self.pagina.wait_for_timeout(100)
        self.assertEqual(self.envios, [])
        self.confirmar('Aceptar todas')
        self.assertEqual(len(self.envios), 1)

    def test_rechazar_todas_envia_una_sola_vez(self):
        self.confirmar('Rechazar todas')
        self.assertEqual(self.envios, [{'accion': ['rechazar_todas']}])

    def test_limite_sigue_enviando_el_valor_elegido(self):
        self.pagina.get_by_role('button', name='Aceptar con límite', exact=True).click()
        self.pagina.locator('#cantidad-maxima-mesas-nuevas').fill('1')
        self.pagina.get_by_role('button', name='Continuar', exact=True).click()
        self.pagina.wait_for_timeout(400)
        self.assertEqual(self.envios, [{'accion': ['aprobar_con_maximo_mesas'], 'maximo_mesas_nuevas': ['1']}])


if __name__ == '__main__':
    unittest.main()
