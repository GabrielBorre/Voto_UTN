const ejemplos = {
  nombre_destinatario: 'María Pérez', nombre_eleccion: 'Elecciones UTN',
  nombre_fecha_administrativa: 'Publicación del padrón', url_accion: 'https://voto.ejemplo.edu.ar',
  sede: 'Campus', mesa: 'K-001', turno: 'Mañana', horario_turno: '08:00 - 13:00',
  claustros: 'Estudiantes', fecha_votacion: '15/11/2026',
};
export const ejemplo = (texto) => texto.replace(/\{(\w+)\}/g, (original, nombre) => ejemplos[nombre] ?? original);

export function iniciarEditor(formulario) {
  function previsualizarNueva() {
    formulario.querySelector('[data-nuevo-asunto]').textContent = ejemplo(formulario.querySelector('[name$="asunto"]').value) || 'Asunto del mensaje';
    formulario.querySelector('[data-nuevo-contenido]').textContent = ejemplo(formulario.querySelector('[name$="contenido"]').value) || 'Escribí el contenido para verlo acá.';
  }
  formulario.querySelectorAll('[data-variable]').forEach((boton) => {
    boton.addEventListener('click', () => {
      const campo = formulario.querySelector('[name$="contenido"]');
      campo.setRangeText(`{${boton.dataset.variable}}`, campo.selectionStart, campo.selectionEnd, 'end');
      campo.focus();
      previsualizarNueva();
    });
  });

  formulario.addEventListener('input', previsualizarNueva);
  previsualizarNueva();
  return previsualizarNueva;
}

document.querySelectorAll("[data-editor-plantilla]").forEach(iniciarEditor);
