const selectorModo = document.querySelector("#id_modo");
const explicaciones = document.querySelectorAll("[data-explicacion-modo]");
const entradaNomina = document.querySelector("[data-entrada-nomina]");
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
      if (formularioModo?.dataset.provisoria === "1" && selectorModo.value === "aleatorio") {
        botonAplicar.dataset.confirm = "Este sorteo es provisorio y puede cambiar antes de la confirmación definitiva. ¿Querés aplicarlo?";
        botonAplicar.dataset.confirmTitle = "Sorteo provisorio";
        botonAplicar.dataset.confirmAccept = "Aplicar sorteo";
      } else {
        delete botonAplicar.dataset.confirm;
        delete botonAplicar.dataset.confirmTitle;
        delete botonAplicar.dataset.confirmAccept;
      }
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
