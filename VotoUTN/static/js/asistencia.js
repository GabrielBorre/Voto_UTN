import { registerAttendance } from './api.js';

export async function submitPage(apiUrl, codes) {
  return registerAttendance(apiUrl, [...codes]);
}

export async function submitManualAttendance(apiUrl, mesaNumero, legajo) {
  return registerAttendance(apiUrl, {
    mesa_numero: mesaNumero,
    legajo,
  });
}
