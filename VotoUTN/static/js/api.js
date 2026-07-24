function csrfToken() {
  return document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1] || '';
}

export async function registerAttendance(url, voterCodes) {
  const response = await fetch(url, { method: 'POST', credentials: 'same-origin', headers: {
    'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'Accept': 'application/json'
  }, body: JSON.stringify({ voter_codes: voterCodes }) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'No fue posible registrar la asistencia.');
  return payload;
}
