let colaDialogos = Promise.resolve();
let dialogo;
let indicador;
let temporizadorCarga;
const operaciones = new Map();
const formulariosEnviados = new Map();
const confirmados = new WeakSet();
const confirmando = new WeakSet();

function crearDialogo() {
  if (dialogo) return dialogo;
  dialogo = document.createElement("dialog");
  dialogo.className = "utn-dialogo";
  dialogo.setAttribute("aria-labelledby", "utn-dialogo-titulo");
  dialogo.setAttribute("aria-describedby", "utn-dialogo-mensaje");
  dialogo.innerHTML = `
    <form method="dialog">
      <h2 id="utn-dialogo-titulo"></h2>
      <p id="utn-dialogo-mensaje"></p>
      <div class="utn-dialogo-entrada" hidden>
        <label for="utn-dialogo-valor">Respuesta</label>
        <input id="utn-dialogo-valor" autocomplete="off">
      </div>
      <div class="utn-dialogo-acciones">
        <button type="button" data-dialogo-cancelar>Cancelar</button>
        <button type="submit" data-dialogo-aceptar>Aceptar</button>
      </div>
    </form>`;
  document.body.append(dialogo);
  dialogo.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape") {
      evento.preventDefault();
      dialogo.close();
    } else if (evento.key === "Tab") {
      const controles = [...dialogo.querySelectorAll("button, input, select, textarea, a[href], [tabindex]")]
        .filter((control) => !control.disabled && control.tabIndex >= 0 && control.getClientRects().length);
      const primero = controles[0];
      const ultimo = controles.at(-1);
      if (evento.shiftKey && document.activeElement === primero) {
        evento.preventDefault();
        ultimo?.focus();
      } else if (!evento.shiftKey && document.activeElement === ultimo) {
        evento.preventDefault();
        primero?.focus();
      }
    }
  });
  return dialogo;
}

function mostrarDialogo(mensaje, opciones) {
  return new Promise((resolver) => {
    const elemento = crearDialogo();
    const anterior = document.activeElement;
    const formulario = elemento.querySelector("form");
    const cancelar = elemento.querySelector("[data-dialogo-cancelar]");
    const aceptar = elemento.querySelector("[data-dialogo-aceptar]");
    const entrada = elemento.querySelector("input");
    const esPregunta = opciones.tipo === "pregunta";
    const esAviso = opciones.tipo === "aviso";
    elemento.querySelector("h2").textContent = opciones.titulo || (esAviso ? "Aviso" : "Confirmar operación");
    elemento.querySelector("p").textContent = mensaje;
    elemento.querySelector(".utn-dialogo-entrada").hidden = !esPregunta;
    entrada.value = opciones.valorInicial || "";
    entrada.type = opciones.tipoEntrada || "text";
    entrada.required = Boolean(opciones.obligatorio);
    entrada.disabled = !esPregunta;
    cancelar.hidden = esAviso;
    aceptar.textContent = opciones.textoAceptar || (esAviso ? "Entendido" : "Confirmar");
    let resultado = esPregunta ? null : false;

    const cerrar = () => {
      elemento.removeEventListener("close", cerrar);
      formulario.removeEventListener("submit", enviar);
      cancelar.removeEventListener("click", cancelarDialogo);
      if (anterior?.isConnected) anterior.focus({ preventScroll: true });
      resolver(resultado);
    };
    const enviar = (evento) => {
      evento.preventDefault();
      resultado = esPregunta ? entrada.value : true;
      elemento.close();
    };
    const cancelarDialogo = () => elemento.close();
    elemento.addEventListener("close", cerrar);
    formulario.addEventListener("submit", enviar);
    cancelar.addEventListener("click", cancelarDialogo);
    elemento.showModal();
    (esPregunta ? entrada : esAviso ? aceptar : cancelar).focus();
  });
}

function encolarDialogo(mensaje, opciones) {
  const pendiente = colaDialogos.then(() => mostrarDialogo(mensaje, opciones));
  colaDialogos = pendiente.catch(() => {});
  return pendiente;
}

export function confirmar(mensaje, opciones = {}) {
  return encolarDialogo(mensaje, { ...opciones, tipo: "confirmacion" });
}

export function avisar(mensaje, opciones = {}) {
  return encolarDialogo(mensaje, { ...opciones, tipo: "aviso" });
}

export function preguntar(mensaje, opciones = {}) {
  return encolarDialogo(mensaje, { ...opciones, tipo: "pregunta" });
}

function actualizarIndicador() {
  if (!indicador) {
    indicador = document.createElement("div");
    indicador.className = "utn-carga";
    indicador.setAttribute("role", "status");
    indicador.setAttribute("aria-live", "polite");
    indicador.setAttribute("aria-atomic", "true");
    indicador.innerHTML = '<span class="utn-throbber" aria-hidden="true"></span><span data-carga-mensaje></span>';
    indicador.hidden = true;
    document.body.append(indicador);
  }
  window.clearTimeout(temporizadorCarga);
  if (!operaciones.size) {
    indicador.hidden = true;
    indicador.querySelector("[data-carga-mensaje]").textContent = "";
    return;
  }
  temporizadorCarga = window.setTimeout(() => {
    indicador.querySelector("[data-carga-mensaje]").textContent = [...operaciones.values()].at(-1);
    indicador.hidden = false;
  }, 300);
}

export function iniciarCarga(mensaje = "Procesando operación…") {
  const clave = Symbol();
  operaciones.set(clave, mensaje);
  actualizarIndicador();
  return () => {
    operaciones.delete(clave);
    actualizarIndicador();
  };
}

export function restablecerCarga() {
  operaciones.clear();
  formulariosEnviados.forEach(({ temporizador }) => window.clearTimeout(temporizador));
  formulariosEnviados.clear();
  actualizarIndicador();
}

function esDescarga(elemento) {
  return elemento.hasAttribute("download") || elemento.hasAttribute("data-download")
    || elemento.hasAttribute("data-no-loading");
}

document.addEventListener("submit", async (evento) => {
  const formulario = evento.target;
  if (!(formulario instanceof HTMLFormElement) || formulario.method === "dialog") return;
  const boton = evento.submitter;
  if (boton?.matches(":disabled") || formulario.closest("fieldset:disabled") || formulariosEnviados.has(formulario)) {
    evento.preventDefault();
    evento.stopImmediatePropagation();
    return;
  }
  if (confirmados.has(formulario)) {
    confirmados.delete(formulario);
    return;
  }
  const mensaje = boton?.dataset.confirm || formulario.dataset.confirm;
  if (!mensaje) return;
  evento.preventDefault();
  evento.stopImmediatePropagation();
  if (confirmando.has(formulario)) return;
  confirmando.add(formulario);
  try {
    const aceptado = await confirmar(mensaje, {
      titulo: boton?.dataset.confirmTitle || formulario.dataset.confirmTitle,
      textoAceptar: boton?.dataset.confirmAccept || formulario.dataset.confirmAccept,
    });
    if (aceptado && formulario.isConnected && !boton?.matches(":disabled")) {
      confirmados.add(formulario);
      try {
        formulario.requestSubmit(boton || undefined);
      } finally {
        confirmados.delete(formulario);
      }
    }
  } finally {
    confirmando.delete(formulario);
  }
}, true);

document.addEventListener("click", async (evento) => {
  const enlace = evento.target.closest("a[data-confirm]");
  if (!enlace || evento.defaultPrevented || evento.button !== 0 || evento.ctrlKey
      || evento.metaKey || evento.shiftKey || evento.altKey) return;
  evento.preventDefault();
  if (await confirmar(enlace.dataset.confirm)) {
    if (enlace.target === "_blank") {
      window.open(enlace.href, "_blank", "noopener");
    } else {
      window.location.assign(enlace.href);
    }
  }
});

document.addEventListener("submit", (evento) => {
  const formulario = evento.target;
  if (!(formulario instanceof HTMLFormElement) || formulario.method === "dialog") return;
  const boton = evento.submitter;
  if (formulariosEnviados.has(formulario)) {
    evento.preventDefault();
    return;
  }
  queueMicrotask(() => {
    const destino = boton?.getAttribute("formtarget") || formulario.target;
    if (evento.defaultPrevented || boton?.matches(":disabled") || esDescarga(formulario)
        || (boton && esDescarga(boton)) || (destino && destino !== "_self")) return;
    const terminar = iniciarCarga(boton?.dataset.loadingMessage || formulario.dataset.loadingMessage);
    // Una descarga o una navegación cancelada no emiten pageshow en la página actual.
    const temporizador = window.setTimeout(() => {
      terminar();
      formulariosEnviados.delete(formulario);
    }, 90000);
    formulariosEnviados.set(formulario, { temporizador, terminar });
  });
});

document.addEventListener("htmx:beforeRequest", (evento) => {
  evento.detail.elt.utnTerminarCarga = iniciarCarga();
});
for (const nombre of ["htmx:afterRequest", "htmx:sendError", "htmx:timeout"]) {
  document.addEventListener(nombre, (evento) => {
    evento.detail.elt.utnTerminarCarga?.();
    delete evento.detail.elt.utnTerminarCarga;
  });
}
window.addEventListener("pageshow", restablecerCarga);
window.addEventListener("pagehide", restablecerCarga);

function mostrarMensajesEmergentes() {
  for (const aviso of document.querySelectorAll("[data-popup-mensaje]")) {
    const mensaje = aviso.textContent.trim();
    const titulo = aviso.dataset.popupTitulo;
    aviso.remove();
    if (mensaje) avisar(mensaje, { titulo });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mostrarMensajesEmergentes, { once: true });
} else {
  mostrarMensajesEmergentes();
}

window.VotoUTN = { confirmar, avisar, preguntar, iniciarCarga, restablecerCarga };
