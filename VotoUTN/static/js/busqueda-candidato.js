// La consulta es informativa: el servidor vuelve a validar el padrón al guardar.
document.querySelectorAll('form[data-busqueda-candidato]').forEach((formulario) => {
  const tipo = formulario.elements.namedItem('tipo_documento');
  const documento = formulario.elements.namedItem('documento');
  const nombre = formulario.elements.namedItem('nombre_padron');
  const estado = formulario.querySelector('[data-estado-busqueda]');
  let temporizador;
  let solicitud;
  let version = 0;

  async function buscar(versionConsulta) {
    if (!documento.value.trim()) return;
    solicitud = new AbortController();
    estado.textContent = 'Buscando en el padrón…';
    const datos = new FormData();
    datos.set('tipo_documento', tipo.value);
    datos.set('documento', documento.value);
    try {
      const respuesta = await fetch(formulario.dataset.busquedaCandidato, {
        method: 'POST', body: datos, signal: solicitud.signal,
        credentials: 'same-origin', cache: 'no-store',
        headers: { 'X-CSRFToken': formulario.elements.namedItem('csrfmiddlewaretoken').value },
      });
      if (versionConsulta !== version) return;
      if (!respuesta.headers.get('content-type')?.includes('application/json')) {
        throw new Error('Respuesta no disponible');
      }
      const resultado = await respuesta.json();
      if (versionConsulta !== version) return;
      nombre.value = respuesta.ok ? resultado.nombre : '';
      estado.textContent = respuesta.ok ? 'Elector encontrado en el padrón de este puesto.' : resultado.error;
    } catch (error) {
      if (error.name !== 'AbortError' && versionConsulta === version) {
        estado.textContent = 'No se pudo consultar el padrón. Volvé a intentar.';
      }
    }
  }

  function actualizar() {
    version += 1;
    solicitud?.abort();
    clearTimeout(temporizador);
    nombre.value = '';
    estado.textContent = 'Ingresá el documento para consultar el nombre.';
    documento.inputMode = tipo.value === 'LEGAJO' ? 'text' : 'numeric';
    const versionConsulta = version;
    temporizador = setTimeout(() => buscar(versionConsulta), 350);
  }
  tipo.addEventListener('change', actualizar);
  documento.addEventListener('input', actualizar);
  actualizar();
});
