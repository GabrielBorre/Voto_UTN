const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const codigo = fs.readFileSync(path.resolve(__dirname, '../static/js/api.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/^export /gm, '');

function cliente(token) {
  const peticiones = [];
  let cargasTerminadas = 0;
  const contexto = {
    document: {
      cookie: 'csrftoken=token-de-otra-instancia; voto_utn_3_csrftoken=token-actual',
      querySelector: selector => {
        assert.equal(selector, '#manual-desktop-form [name="csrfmiddlewaretoken"]');
        return token ? { value: token } : null;
      },
    },
    iniciarCarga: () => () => { cargasTerminadas += 1; },
    fetch: async (url, opciones) => {
      peticiones.push({ url, opciones });
      return { ok: true, json: async () => ({ recibido: true }) };
    },
  };
  vm.createContext(contexto);
  vm.runInContext(codigo, contexto);
  return { contexto, peticiones, cargasTerminadas: () => cargasTerminadas };
}

test('QR de mesa y carga manual usan el token de la pagina, no otra cookie', async () => {
  const { contexto, peticiones, cargasTerminadas } = cliente('token-enmascarado-de-django');
  await contexto.gestionarMesa('/api/mesa/', { accion: 'consultar', codigo_qr: 'M1.prueba' });
  await contexto.registrarAsistencia('/api/lote/', { mesa_codigo: 'K-001', dni: '40000001' });
  for (const { opciones } of peticiones) {
    assert.equal(opciones.headers['X-CSRFToken'], 'token-enmascarado-de-django');
    assert.equal(opciones.credentials, 'same-origin');
  }
  assert.deepEqual(JSON.parse(peticiones[0].opciones.body), { accion: 'consultar', codigo_qr: 'M1.prueba' });
  assert.deepEqual(JSON.parse(peticiones[1].opciones.body), { mesa_codigo: 'K-001', dni: '40000001' });
  assert.equal(cargasTerminadas(), 2);
});

test('sin token informa el error, no envia el POST y cierra el indicador de carga', async () => {
  const { contexto, peticiones, cargasTerminadas } = cliente(null);
  await assert.rejects(contexto.gestionarMesa('/api/mesa/', {}), /Recargá la página/);
  assert.equal(peticiones.length, 0);
  assert.equal(cargasTerminadas(), 1);
});
