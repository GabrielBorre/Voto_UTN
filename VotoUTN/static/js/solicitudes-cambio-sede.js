import { iniciarCarga } from "./interfaz.js";

const botonAbrir = document.getElementById("abrir-dialogo-limite-mesas");
const dialogo = document.getElementById("dialogo-limite-mesas");
const formularioDialogo = document.getElementById("formulario-dialogo-limite-mesas");
const formularioResolucion = document.getElementById("formulario-aprobar-con-limite-mesas");
const entradaMaximo = document.getElementById("cantidad-maxima-mesas-nuevas");
const maximoOculto = document.getElementById("maximo_mesas_nuevas");
const botonCancelar = document.getElementById("cancelar-dialogo-limite-mesas");

const casillas = [...document.querySelectorAll(".seleccion-solicitud")];
const seleccionarTodas = document.getElementById("seleccionar-todas-solicitudes");
const cantidadSeleccionadas = document.getElementById("cantidad-seleccionadas");
const aprobarSeleccionadas = document.getElementById("boton-aprobar-seleccionadas");
const totalMesas = document.getElementById("total-mesas-seleccionadas");
const errorEstimacion = document.getElementById("error-estimacion-mesas");
const celdasEstimacion = [...document.querySelectorAll("[data-estimacion-sede]")];

if (seleccionarTodas && cantidadSeleccionadas && aprobarSeleccionadas && totalMesas && errorEstimacion) {
  let consultaActual = 0;
  let solicitud;

  async function actualizarEstimacion() {
    const consulta = ++consultaActual;
    solicitud?.abort();
    const seleccionadas = casillas.filter((casilla) => casilla.checked && !casilla.matches(":disabled"));
    const disponibles = casillas.filter((casilla) => !casilla.matches(":disabled"));
    cantidadSeleccionadas.textContent = String(seleccionadas.length);
    aprobarSeleccionadas.disabled = true;
    seleccionarTodas.checked = disponibles.length > 0 && seleccionadas.length === disponibles.length;
    seleccionarTodas.indeterminate = seleccionadas.length > 0 && seleccionadas.length < disponibles.length;
    errorEstimacion.hidden = true;
    errorEstimacion.textContent = "";

    if (!seleccionadas.length) {
      totalMesas.textContent = "0";
      celdasEstimacion.forEach((celda) => { celda.textContent = "0"; });
      return;
    }

    const controlador = new AbortController();
    solicitud = controlador;
    const url = new URL(window.location.href);
    url.search = "";
    url.searchParams.set("accion", "estimar_seleccion");
    seleccionadas.forEach((casilla) => url.searchParams.append("solicitudes_ids", casilla.value));
    totalMesas.textContent = "Calculando…";
    celdasEstimacion.forEach((celda) => { celda.textContent = "…"; });
    const terminarCarga = iniciarCarga("Calculando mesas de las solicitudes seleccionadas…");
    try {
      const respuesta = await fetch(url, {
        headers: { "Accept": "application/json" },
        credentials: "same-origin",
        cache: "no-store",
        signal: controlador.signal,
      });
      const datos = await respuesta.json();
      if (consulta !== consultaActual) return;
      if (!respuesta.ok) throw new Error(datos.error || "No se pudo estimar la cantidad de mesas.");
      if (!datos.mesas_por_sede || !Number.isInteger(datos.total) || datos.total < 0) {
        throw new Error("No se pudo interpretar la estimación de mesas.");
      }
      celdasEstimacion.forEach((celda) => {
        celda.textContent = String(datos.mesas_por_sede[celda.dataset.estimacionSede] || 0);
      });
      totalMesas.textContent = String(datos.total);
      aprobarSeleccionadas.disabled = Boolean(aprobarSeleccionadas.closest("fieldset:disabled"));
    } catch (error) {
      if (consulta !== consultaActual || error.name === "AbortError") return;
      errorEstimacion.textContent = error.message || "No se pudo estimar la cantidad de mesas.";
      errorEstimacion.hidden = false;
      totalMesas.textContent = "No disponible";
      celdasEstimacion.forEach((celda) => { celda.textContent = "—"; });
    } finally {
      terminarCarga();
      if (consulta === consultaActual) solicitud = null;
    }
  }

  casillas.forEach((casilla) => casilla.addEventListener("change", actualizarEstimacion));
  seleccionarTodas.addEventListener("change", () => {
    casillas.filter((casilla) => !casilla.matches(":disabled")).forEach((casilla) => {
      casilla.checked = seleccionarTodas.checked;
    });
    actualizarEstimacion();
  });
  window.addEventListener("pageshow", actualizarEstimacion);
  window.addEventListener("pagehide", () => {
    consultaActual += 1;
    solicitud?.abort();
  });
  actualizarEstimacion();
}

if (
  botonAbrir &&
  dialogo &&
  formularioDialogo &&
  formularioResolucion &&
  entradaMaximo &&
  maximoOculto &&
  botonCancelar
) {
  botonAbrir.addEventListener("click", () => {
    dialogo.showModal();
    entradaMaximo.focus();
  });

  botonCancelar.addEventListener("click", () => {
    dialogo.close();
  });

  entradaMaximo.addEventListener("input", () => {
    entradaMaximo.setCustomValidity("");
  });

  formularioDialogo.addEventListener("submit", (evento) => {
    evento.preventDefault();
    if (!entradaMaximo.value || !entradaMaximo.checkValidity()) {
      entradaMaximo.reportValidity();
      return;
    }

    const maximo = Number(entradaMaximo.value);
    if (!Number.isInteger(maximo) || maximo < 0) {
      entradaMaximo.setCustomValidity("Ingresá un número entero mayor o igual a cero.");
      entradaMaximo.reportValidity();
      return;
    }

    maximoOculto.value = String(maximo);
    dialogo.close();
    formularioResolucion.requestSubmit();
  });
}
