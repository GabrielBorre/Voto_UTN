const modal = document.querySelector('#modal-calendario');
document.querySelector('[data-abrir-calendario]')?.addEventListener('click', () => modal.showModal());
document.querySelector('[data-cerrar-calendario]')?.addEventListener('click', () => modal.close());
document.querySelectorAll('[data-calendario]').forEach((seccion) => {
  const sugeridas = JSON.parse(seccion.querySelector('#plantillas-calendario').textContent);
  seccion.addEventListener('change', (evento) => {
    if (!evento.target.name?.match(/-(fecha_administrativa|recordatorio)$/)) return;
    const fila = evento.target.closest('[data-mensaje]');
    const fecha = fila.querySelector('[name$="-fecha_administrativa"]').value;
    const recordatorio = fila.querySelector('[name$="-recordatorio"]').checked;
    fila.querySelector('[name$="-plantilla"]').value = sugeridas[fecha]?.[recordatorio ? 'recordatorio' : 'principal'] ?? '';
  });
  seccion.querySelector('[data-agregar-mensaje]').addEventListener('click', () => {
    const total = seccion.querySelector('[name="mensajes-TOTAL_FORMS"]');
    const html = seccion.querySelector('[data-mensaje-vacio]').innerHTML.replaceAll('__prefix__', total.value);
    seccion.querySelector('[data-mensajes]').insertAdjacentHTML('beforeend', html);
    total.value = Number(total.value) + 1;
  });
});
