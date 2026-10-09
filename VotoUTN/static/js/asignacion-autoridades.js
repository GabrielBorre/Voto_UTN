const formulario = document.querySelector("[data-asignacion-autoridad]");

if (formulario) {
  const selectorClaustro = formulario.querySelector("select[name='manual-claustro']");
  const selectorMesa = formulario.querySelector("select[name='manual-mesa']");
  const selectorPersona = formulario.querySelector("select[name='manual-candidatura']");
  const mensaje = formulario.querySelector("[data-mensaje-candidatos]");
  const boton = formulario.querySelector("[data-enviar-asignacion]");
  const opcionesMesas = [...selectorMesa.options].filter((opcion) => opcion.value);
  const opcionesPersonas = [...selectorPersona.options].filter((opcion) => opcion.value);

  const actualizarOpciones = ({ limpiar = false } = {}) => {
    const idClaustro = selectorClaustro.value;
    let mesasCompatibles = 0;
    let personasCompatibles = 0;

    for (const opcion of opcionesMesas) {
      const compatible = Boolean(idClaustro) && opcion.dataset.claustro === idClaustro;
      opcion.hidden = !compatible;
      opcion.disabled = !compatible;
      if (compatible) mesasCompatibles += 1;
    }

    for (const opcion of opcionesPersonas) {
      const compatible = Boolean(idClaustro) && opcion.dataset.claustro === idClaustro;
      opcion.hidden = !compatible;
      opcion.disabled = !compatible;
      if (compatible) personasCompatibles += 1;
    }

    if (limpiar || selectorMesa.selectedOptions[0]?.disabled) selectorMesa.value = "";
    if (limpiar || selectorPersona.selectedOptions[0]?.disabled) selectorPersona.value = "";

    selectorMesa.disabled = !idClaustro || mesasCompatibles === 0;
    selectorPersona.disabled = !idClaustro || !selectorMesa.value || personasCompatibles === 0;

    selectorMesa.options[0].textContent = !idClaustro
      ? "Elegí primero un claustro"
      : mesasCompatibles
        ? "Seleccioná una mesa"
        : "No hay mesas configuradas para este claustro";
    selectorPersona.options[0].textContent = !idClaustro
      ? "Elegí primero un claustro y una mesa"
      : personasCompatibles
        ? "Seleccioná una persona"
        : "No hay personas candidatas de este claustro";

    mensaje.textContent = !idClaustro
      ? "Elegí un claustro para ver sus mesas y personas candidatas."
      : !mesasCompatibles
        ? "Este claustro todavía no tiene mesas configuradas."
        : !personasCompatibles
          ? "Todavía no hay personas candidatas cargadas para este claustro."
          : `${mesasCompatibles} mesa${mesasCompatibles === 1 ? "" : "s"} y ${personasCompatibles} persona${personasCompatibles === 1 ? "" : "s"} disponibles para este claustro.`;
    boton.disabled = !selectorClaustro.value || !selectorMesa.value || !selectorPersona.value;
  };

  selectorClaustro.addEventListener("change", () => actualizarOpciones({ limpiar: true }));
  selectorMesa.addEventListener("change", () => {
    selectorPersona.value = "";
    actualizarOpciones();
  });
  selectorPersona.addEventListener("change", actualizarOpciones);
  actualizarOpciones();
}
