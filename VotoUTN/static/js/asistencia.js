import { registerAttendance } from './api.js';

export async function submitPage(apiUrl, codes) {
  return registerAttendance(apiUrl, [...codes]);
}
