const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const rutaModulo = process.env.MODULO_INTERFAZ
  || path.resolve(__dirname, '../static/js/interfaz.js');
// El módulo no tiene imports; se retiran solo las declaraciones de exportación
// para ejecutar sus eventos reales en contextos de página independientes.
const rutaPosicion = path.resolve(__dirname, '../static/js/conservar-posicion.js');
const codigo = fs.readFileSync(rutaModulo, 'utf8').replace(/^export /gm, '')
  + '\n' + fs.readFileSync(rutaPosicion, 'utf8');
const clave = 'utn:posicion-pagina';

function pagina(url, almacenamiento = new Map(), posicion = {}, estadoCarga = 'complete') {
  const eventosDocumento = new Map();
  const eventosVentana = new Map();
  const desplazamientos = [];
  const registrar = (eventos, nombre, accion) => {
    if (!eventos.has(nombre)) eventos.set(nombre, []);
    eventos.get(nombre).push(accion);
  };
  const almacenamientoSesion = almacenamiento instanceof Map ? {
    getItem: nombre => almacenamiento.get(nombre) ?? null,
    setItem: (nombre, valor) => almacenamiento.set(nombre, valor),
    removeItem: nombre => almacenamiento.delete(nombre),
  } : almacenamiento;
  const ventana = {
    location: new URL(url), scrollX: posicion.x || 0, scrollY: posicion.y || 0,
    addEventListener: (nombre, accion) => registrar(eventosVentana, nombre, accion),
    clearTimeout: () => {}, setTimeout: () => 1, requestAnimationFrame: accion => accion(),
    scrollTo: (x, y) => {
      desplazamientos.push([x, y]);
      ventana.scrollX = x;
      ventana.scrollY = y;
    },
  };
  const documento = {
    readyState: estadoCarga, activeElement: null,
    addEventListener: (nombre, accion) => registrar(eventosDocumento, nombre, accion),
    querySelectorAll: () => [],
    body: {append: () => {}},
    createElement: () => ({setAttribute: () => {}, querySelector: () => ({textContent: ''})}),
  };
  vm.runInNewContext(codigo, {
    document: documento, window: ventana, sessionStorage: almacenamientoSesion,
    HTMLFormElement: class {}, URL, queueMicrotask,
  });
  return {
    ventana, desplazamientos,
    abandonar: () => eventosVentana.get('pagehide').forEach(accion => accion({})),
    mostrar: () => eventosVentana.get('pageshow').forEach(accion => accion({})),
    pulsarSinNavegar: () => eventosDocumento.get('click').forEach(accion => accion({
      target: {closest: () => null}, button: 0, defaultPrevented: false,
    })),
  };
}

test('un POST que vuelve a las reglas conserva su posición', () => {
  const almacenamiento = new Map();
  pagina('http://localhost/padron/reglas/', almacenamiento, {y: 780}).abandonar();
  const respuesta = pagina('http://localhost/padron/reglas/', almacenamiento);
  assert.deepEqual(respuesta.desplazamientos, [[0, 780]]);
});

test('filtrar o paginar la misma ruta conserva la posición', () => {
  const almacenamiento = new Map();
  pagina('http://localhost/padron/reglas/?estado=asignada', almacenamiento, {y: 930}).abandonar();
  const respuesta = pagina('http://localhost/padron/reglas/?estado=pendiente&pagina=2', almacenamiento);
  assert.deepEqual(respuesta.desplazamientos, [[0, 930]]);
});

test('también conserva el desplazamiento horizontal de una pantalla', () => {
  const almacenamiento = new Map();
  pagina('http://localhost/padron/reglas/', almacenamiento, {x: 120, y: 470}).abandonar();
  assert.deepEqual(pagina('http://localhost/padron/reglas/', almacenamiento).desplazamientos, [[120, 470]]);
});

test('cambiar de pantalla consume el dato sin trasladar la posición', () => {
  const almacenamiento = new Map();
  pagina('http://localhost/padron/reglas/', almacenamiento, {y: 930}).abandonar();
  assert.deepEqual(pagina('http://localhost/mesas/', almacenamiento).desplazamientos, []);
  assert.equal(almacenamiento.has(clave), false);
  assert.deepEqual(pagina('http://localhost/padron/reglas/', almacenamiento).desplazamientos, []);
});

test('los enlaces a una sección respetan su ancla', () => {
  const almacenamiento = new Map();
  pagina('http://localhost/autoridades/', almacenamiento, {y: 930}).abandonar();
  assert.deepEqual(pagina('http://localhost/autoridades/?turno=2#seleccion', almacenamiento).desplazamientos, []);
});

test('captura la posición al salir y no una posición anterior a la acción', () => {
  const almacenamiento = new Map();
  const origen = pagina('http://localhost/padron/reglas/', almacenamiento, {y: 100});
  origen.ventana.scrollY = 1240;
  origen.abandonar();
  assert.deepEqual(pagina('http://localhost/padron/reglas/', almacenamiento).desplazamientos, [[0, 1240]]);
});

test('una interacción sin navegación no deja una restauración pendiente', () => {
  const almacenamiento = new Map();
  pagina('http://localhost/padron/reglas/', almacenamiento, {y: 540}).pulsarSinNavegar();
  assert.equal(almacenamiento.size, 0);
});

test('un dato corrupto o una coordenada inválida no rompe la interfaz', () => {
  for (const dato of ['{invalido', 'null', '{"ruta":"/padron/","y":-10}', '{"ruta":"/padron/","y":"500"}']) {
    const almacenamiento = new Map([[clave, dato]]);
    const respuesta = pagina('http://localhost/padron/', almacenamiento);
    assert.deepEqual(respuesta.desplazamientos, []);
    assert.equal(typeof respuesta.ventana.VotoUTN.confirmar, 'function');
  }
});

test('el bloqueo de almacenamiento no impide cargar ni abandonar la página', () => {
  const almacenamiento = {
    getItem: () => { throw new Error('Almacenamiento bloqueado'); },
    setItem: () => { throw new Error('Almacenamiento bloqueado'); },
  };
  const respuesta = pagina('http://localhost/padron/', almacenamiento);
  assert.equal(typeof respuesta.ventana.VotoUTN.confirmar, 'function');
  assert.doesNotThrow(respuesta.abandonar);
});

test('acepta una posición guardada con la versión anterior del módulo', () => {
  const almacenamiento = new Map([['utn:scroll-conservado', JSON.stringify({ruta: '/padron/', y: 420})]]);
  assert.deepEqual(pagina('http://localhost/padron/', almacenamiento).desplazamientos, [[0, 420]]);
});


test('espera al final de carga antes de restaurar la posición', () => {
  const almacenamiento = new Map([[clave, JSON.stringify({ruta: '/padron/', y: 780})]]);
  const respuesta = pagina('http://localhost/padron/', almacenamiento, {}, 'interactive');
  assert.deepEqual(respuesta.desplazamientos, []);
  respuesta.mostrar();
  assert.deepEqual(respuesta.desplazamientos, [[0, 780]]);
});
