const statusElement = document.querySelector("#camera-status");
const countElement = document.querySelector("#qr-count");
const mesaElement = document.querySelector("#detected-mesa");
const registerButton = document.querySelector("#register-page");
const summaryElement = document.querySelector("#last-page-summary");

/* Iconos SVG preservados para no perderlos al cambiar innerHTML */
const ICONS = {
  register: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7v14a2 2 0 0 0 2 2h14"></path><path d="M3 7l4.5 4.5L12 3l4.5 8.5L21 7"></path><rect x="9" y="13" width="6" height="6" rx="1"></rect></svg>`,
  manual: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`
};

export function setStatus(text, tone = "info") {
  statusElement.textContent = text;
  statusElement.classList.remove("status-success", "status-error");

  if (tone === "success") {
    statusElement.classList.add("status-success");
  }

  if (tone === "error") {
    statusElement.classList.add("status-error");
  }
}

export function setCount(count) {
  if (!countElement) {
    return;
  }

  countElement.textContent = `QRs escaneados en mesa: ${count}`;
}

export function setRegisterButtonLabel(mesaNumber, count) {
  const qrLabel = count === 1 ? "QR" : "QRs";
  const label = mesaNumber
    ? `Registrar Mesa ${mesaNumber}<br>${count} ${qrLabel}`
    : `Registrar Mesa<br>${count} ${qrLabel}`;
  registerButton.innerHTML = `${ICONS.register} ${label}`;
}