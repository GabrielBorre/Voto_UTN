function csrfToken() {
  return document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
}

export async function registrarAsistencia(url, codigosQr) {
  const body = Array.isArray(codigosQr) ? { codigos_qr: codigosQr } : codigosQr;
  const response = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: {
    'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'Accept': 'application/json'
  }, body: JSON.stringify(body) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'No fue posible registrar la asistencia.');
  return payload;
}
