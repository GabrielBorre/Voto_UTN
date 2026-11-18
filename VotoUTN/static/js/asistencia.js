import { gestionarMesa as enviarGestionMesa, registrarAsistencia } from './api.js?v=20261117.1';

export async function submitPage(apiUrl, codes, mesaCodigo) {
  return registrarAsistencia(apiUrl, { codigos_qr: [...codes], mesa_codigo: mesaCodigo });
}

export function gestionarMesa(apiUrl, cuerpo) {
  return enviarGestionMesa(apiUrl, cuerpo);
}

export async function submitManualAttendance(apiUrl, mesaCodigo, dni) {
  return registrarAsistencia(apiUrl, {
    mesa_codigo: mesaCodigo,
    dni,
  });
}
