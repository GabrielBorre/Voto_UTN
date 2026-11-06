const datos = document.getElementById("personas-disponibles");
const turno = document.getElementById("id_turno");
const busqueda = document.getElementById("id_busqueda");
const personas = document.getElementById("id_registro");
const resultado = document.querySelector("[data-resultados-personas]");

if (datos && turno && busqueda && personas) {
  const disponibles = JSON.parse(datos.textContent);
  const normalizar = (texto) => texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const actualizar = () => {
    const elegida = personas.value;
    const palabras = normalizar(busqueda.value).trim().split(/\s+/).filter(Boolean);
    const compatibles = disponibles.filter((persona) => persona.turnos.includes(Number(turno.value)));
    const coincidencias = compatibles.filter((persona) => palabras.every((palabra) => normalizar(persona.nombre).includes(palabra)));
    personas.replaceChildren(new Option("Seleccioná una persona", ""));
    for (const persona of coincidencias) {
      personas.add(new Option(persona.nombre, String(persona.id), false, String(persona.id) === elegida));
    }
    if (resultado) {
      resultado.textContent = coincidencias.length
        ? `${coincidencias.length} personas disponibles para el turno elegido.`
        : compatibles.length
          ? "No hay coincidencias con esa búsqueda. Probá otro nombre, documento o legajo."
          : "No hay personas disponibles y compatibles con este turno en la mesa.";
    }
  };
  turno.addEventListener("change", actualizar);
  busqueda.addEventListener("input", actualizar);
  actualizar();
}
