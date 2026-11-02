const selectorModo = document.querySelector("#id_modo");
const explicaciones = document.querySelectorAll("[data-explicacion-modo]");
const entradaNomina = document.querySelector("[data-entrada-nomina]");
const opcionesNomina = document.querySelector("[data-opciones-nomina]");
const archivoNomina = entradaNomina?.querySelector("input[type='file']");
let botonAplicar = document.querySelector("[data-boton-aplicar]");
const accionesModo = document.querySelector("[data-acciones-modo]");
const botonRecalcular = document.querySelector("[data-boton-recalcular]");
const formularioModo = document.querySelector("#formulario-modo-autoridades");
const selectorTurnos = document.querySelector("input[name='configuracion-turnos']")?.form;

for (const boton of document.querySelectorAll("[data-detalle-mesa]")) {
  boton.addEventListener("click", () => {
    const detalle = document.getElementById(boton.dataset.detalleMesa);
    if (!detalle) return;
    detalle.hidden = !detalle.hidden;
    boton.setAttribute("aria-expanded", String(!detalle.hidden));
    boton.textContent = detalle.hidden ? "Ver autoridades" : "Ocultar autoridades";
  });
}

const actualizarCuposTurnos = () => {
  const formulario = selectorTurnos;
  if (!formulario) return;
  const seleccionados = new Set(
    [...formulario.querySelectorAll("input[name='configuracion-turnos']:checked")].map((entrada) => entrada.value),
  );
  for (const fila of formulario.querySelectorAll("[data-turno-cupos]")) {
    fila.hidden = !seleccionados.has(fila.dataset.turnoCupos);
  }
};

if (selectorTurnos) {
  selectorTurnos.addEventListener("change", actualizarCuposTurnos);
  actualizarCuposTurnos();
}

if (selectorModo && explicaciones.length) {
  const actualizarExplicacion = () => {
    for (const explicacion of explicaciones) {
      explicacion.hidden = explicacion.dataset.explicacionModo !== selectorModo.value;
    }
    if (entradaNomina) {
      entradaNomina.hidden = selectorModo.value !== "nomina";
    }
    if (opcionesNomina) {
      opcionesNomina.hidden = selectorModo.value !== "nomina";
    }
    if (archivoNomina) {
      archivoNomina.required = selectorModo.value === "nomina";
    }
    const textoAplicar = {
      nomina: "Previsualizar nómina",
      aleatorio: "Sortear todas las mesas",
    }[selectorModo.value];
    if (!textoAplicar) {
      botonAplicar?.remove();
      botonAplicar = null;
    } else if (accionesModo) {
      if (!botonAplicar) {
        botonAplicar = document.createElement("button");
        botonAplicar.type = "submit";
        botonAplicar.name = "aplicar-modo";
        botonAplicar.className = "button primary";
        botonAplicar.dataset.botonAplicar = "";
        accionesModo.prepend(botonAplicar);
      }
      botonAplicar.textContent = textoAplicar;
    }
    if (botonRecalcular) {
      botonRecalcular.hidden = selectorModo.value !== formularioModo?.dataset.modoGuardado;
    }
  };

  selectorModo.addEventListener("input", actualizarExplicacion);
  selectorModo.addEventListener("change", () => {
    actualizarExplicacion();
  });
  actualizarExplicacion();
}

for (const opcion of opcionesNomina?.querySelectorAll("input[type='checkbox']") || []) {
  opcion.addEventListener("change", () => {
    const reacomodar = opcionesNomina.querySelector("input[name='reacomodar_titulares']");
    const mesaDistinta = opcionesNomina.querySelector("input[name='permitir_mesa_distinta']");
    const sede = opcionesNomina.querySelector("input[name='permitir_cambio_sede']");
    if (opcion === sede && sede.checked) {
      reacomodar.checked = true;
      mesaDistinta.checked = false;
    }
    if (opcion === reacomodar && reacomodar.checked) mesaDistinta.checked = false;
    if (opcion === reacomodar && !reacomodar.checked) sede.checked = false;
    if (opcion === mesaDistinta && mesaDistinta.checked) {
      reacomodar.checked = false;
      sede.checked = false;
    }
    if (selectorModo.value !== "nomina" || formularioModo.dataset.modoGuardado !== "nomina") return;
    if (!Number(formularioModo.dataset.nominaCargada)) return;
    // Al cargar un archivo se aplican juntas sus opciones. Con una nómina ya
    // guardada, cambiar una opción actualiza automáticamente la distribución.
    if (archivoNomina?.files.length) return;
    archivoNomina.required = false;
    const accion = document.createElement("input");
    accion.type = "hidden";
    accion.name = "actualizar-nomina";
    accion.value = "1";
    formularioModo.append(accion);
    formularioModo.requestSubmit();
  });
}
