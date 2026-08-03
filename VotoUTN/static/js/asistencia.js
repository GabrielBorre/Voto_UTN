import { registrarAsistencia } from './api.js';

export async function submitPage(apiUrl, codes) {
  return registrarAsistencia(apiUrl, [...codes]);
}

export async function submitManualAttendance(apiUrl, mesaNumero, legajo) {
  return registrarAsistencia(apiUrl, {
    mesa_numero: mesaNumero,
    legajo,
  });
}
