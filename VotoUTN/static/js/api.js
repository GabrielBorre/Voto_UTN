import { iniciarCarga } from "./interfaz.js";

function csrfToken() {
  const token = document.querySelector('#manual-desktop-form [name="csrfmiddlewaretoken"]')?.value;
  if (!token) throw new Error('No se pudo obtener el token CSRF. Recargá la página e intentá nuevamente.');
  return token;
}

async function postJson(url, body) {
  const terminarCarga = iniciarCarga("Procesando registro…");
  try {
    const response = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: {
      'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'Accept': 'application/json'
    }, body: JSON.stringify(body) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'No fue posible completar la operación.');
    return payload;
  } finally {
    terminarCarga();
  }
}

export function registrarAsistencia(url, codigosQr) {
  return postJson(url, Array.isArray(codigosQr) ? { codigos_qr: codigosQr } : codigosQr);
}

export function gestionarMesa(url, cuerpo) {
  return postJson(url, cuerpo);
}
