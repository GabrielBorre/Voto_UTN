const catalogo = JSON.parse(document.querySelector('#catalogo-plantillas').textContent);
const dialogo = document.querySelector('#crear-plantilla-dialogo');
const formulario = document.querySelector('#crear-plantilla-form');
const ejemplos = {
  nombre_destinatario: 'María Pérez', nombre_eleccion: 'Elecciones UTN',
  nombre_fecha_administrativa: 'Publicación del padrón', url_accion: 'https://voto.ejemplo.edu.ar',
  sede: 'Campus', mesa: 'K-001', turno: 'Mañana', horario_turno: '08:00 - 13:00',
  claustros: 'Estudiantes', fecha_votacion: '15/11/2026',
};
const ejemplo = (texto) => texto.replace(/\{(\w+)\}/g, (original, nombre) => ejemplos[nombre] ?? original);
const etiquetas = {elector: 'Electores', autoridad_mesa: 'Autoridades de mesa', administrador_junta: 'Administradores de junta', administrativo_junta: 'Administrativos de junta'};
let destino;
let enviando = false;

function mostrarPlantilla(selector) {
  const panel = document.querySelector(`[data-preview="${selector.id}"]`);
  const plantilla = catalogo.find((item) => String(item.id) === selector.value);
  panel.querySelector('[data-asunto]').textContent = plantilla ? ejemplo(plantilla.asunto) : 'Elegí una plantilla';
  panel.querySelector('[data-contenido]').textContent = plantilla ? ejemplo(plantilla.contenido) : 'Acá vas a ver el asunto y el contenido antes de guardar.';
  panel.querySelector('[data-destinatarios]').textContent = plantilla ? `Destinatarios: ${plantilla.roles_destinatarios.map((rol) => etiquetas[rol] ?? rol).join(', ')}` : '';
}

document.querySelectorAll('[data-config-mensaje]').forEach((seccion) => {
  const habilitar = seccion.querySelector('.fecha-interruptor input');
  const actualizar = () => {
    seccion.querySelector('[data-opciones-mensaje]').hidden = !habilitar.checked;
    seccion.querySelector('[data-mensaje-inactivo]').hidden = habilitar.checked;
  };
  habilitar.addEventListener('change', actualizar);
  actualizar();
  const selector = seccion.querySelector('select');
  selector.addEventListener('change', () => mostrarPlantilla(selector));
  mostrarPlantilla(selector);
});

function previsualizarNueva() {
  formulario.querySelector('[data-nuevo-asunto]').textContent = ejemplo(formulario.elements['nueva-asunto'].value) || 'Asunto del mensaje';
  formulario.querySelector('[data-nuevo-contenido]').textContent = ejemplo(formulario.elements['nueva-contenido'].value) || 'Escribí el contenido para verlo acá.';
}
formulario.addEventListener('input', previsualizarNueva);
previsualizarNueva();

document.querySelectorAll('[data-crear-plantilla]').forEach((boton) => {
  boton.addEventListener('click', () => {
    destino = document.getElementById(boton.dataset.crearPlantilla);
    formulario.reset();
    formulario.querySelector('[data-errores-plantilla]').replaceChildren();
    const roles = [...document.querySelectorAll('#fecha-administrativa [name="roles_destinatarios"]:checked')].map((campo) => campo.value);
    formulario.querySelectorAll('[name="nueva-roles_destinatarios"]').forEach((campo) => { campo.checked = roles.includes(campo.value); });
    previsualizarNueva();
    dialogo.showModal();
  });
});
document.querySelectorAll('[data-cerrar-plantilla]').forEach((boton) => boton.addEventListener('click', () => { if (!enviando) dialogo.close(); }));
dialogo.addEventListener('cancel', (evento) => { if (enviando) evento.preventDefault(); });
formulario.querySelectorAll('[data-variable]').forEach((boton) => {
  boton.addEventListener('click', () => {
    const campo = formulario.elements['nueva-contenido'];
    campo.setRangeText(`{${boton.dataset.variable}}`, campo.selectionStart, campo.selectionEnd, 'end');
    campo.focus();
    previsualizarNueva();
  });
});

formulario.addEventListener('submit', async (evento) => {
  evento.preventDefault();
  if (enviando) return;
  enviando = true;
  const boton = formulario.querySelector('[data-guardar-plantilla]');
  const errores = formulario.querySelector('[data-errores-plantilla]');
  boton.disabled = true;
  boton.textContent = 'Guardando…';
  errores.replaceChildren();
  try {
    const respuesta = await fetch(formulario.action, {method: 'POST', body: new FormData(formulario), headers: {'Accept': 'application/json'}, credentials: 'same-origin'});
    if (respuesta.redirected || !respuesta.headers.get('content-type')?.includes('application/json')) {
      throw new Error('No se pudo guardar. Verificá tu sesión en otra pestaña y volvé a intentar; los datos siguen acá.');
    }
    const datos = await respuesta.json();
    if (!respuesta.ok) {
      for (const [campo, mensajes] of Object.entries(datos.errores ?? {})) {
        const etiqueta = formulario.querySelector(`label[for="id_nueva-${campo}"]`)?.textContent ?? campo;
        for (const mensaje of mensajes) {
          const linea = document.createElement('p');
          linea.className = 'error';
          linea.textContent = `${etiqueta}: ${mensaje.message}`;
          errores.append(linea);
        }
      }
      errores.focus();
      return;
    }
    const plantilla = datos.plantilla;
    catalogo.push(plantilla);
    document.querySelectorAll('[data-config-mensaje] select').forEach((selector) => selector.add(new Option(plantilla.nombre, plantilla.id)));
    destino.value = String(plantilla.id);
    mostrarPlantilla(destino);
    document.querySelector('#estado-plantilla').textContent = `Se creó «${plantilla.nombre}» en el catálogo. Guardá la fecha para conservar la selección.`;
    dialogo.close();
    destino.focus();
  } catch (error) {
    errores.textContent = error.message || 'No se pudo guardar la plantilla. Intentá nuevamente.';
    errores.focus();
  } finally {
    enviando = false;
    boton.disabled = false;
    boton.textContent = 'Crear y seleccionar';
  }
});
