const CLAVE_POSICION_PAGINA = "utn:posicion-pagina";
const CLAVE_POSICION_ANTERIOR = "utn:scroll-conservado";

window.addEventListener("pagehide", () => {
  try {
    sessionStorage.setItem(CLAVE_POSICION_PAGINA, JSON.stringify({
      ruta: window.location.pathname,
      x: window.scrollX,
      y: window.scrollY,
    }));
  } catch {
    // El almacenamiento bloqueado no debe impedir navegar.
  }
});

function leerPosicionPendiente() {
  try {
    const guardado = sessionStorage.getItem(CLAVE_POSICION_PAGINA)
      || sessionStorage.getItem(CLAVE_POSICION_ANTERIOR);
    sessionStorage.removeItem(CLAVE_POSICION_PAGINA);
    sessionStorage.removeItem(CLAVE_POSICION_ANTERIOR);
    if (!guardado) return null;
    const { ruta, x, y } = JSON.parse(guardado);
    if (ruta !== window.location.pathname || window.location.hash || !Number.isFinite(y) || y < 0) return null;
    return { x: Number.isFinite(x) && x >= 0 ? x : 0, y };
  } catch {
    return null;
  }
}

const posicionPendiente = leerPosicionPendiente();
function restaurarPosicion() {
  if (!posicionPendiente) return;
  // Esperar al diseño final evita que una restauración temprana se pierda al cargar.
  window.requestAnimationFrame(() => {
    window.scrollTo(posicionPendiente.x, posicionPendiente.y);
  });
}

if (document.readyState === "complete") {
  restaurarPosicion();
} else {
  window.addEventListener("pageshow", restaurarPosicion, { once: true });
}
