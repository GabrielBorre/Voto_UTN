const statusElement = document.querySelector("#camera-status");
const countElement = document.querySelector("#qr-count");
const mesaElement = document.querySelector("#detected-mesa");

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

  countElement.textContent = String(count);
}

export function setMesaCodigo(mesaCodigo) {
  mesaElement.textContent = mesaCodigo ? `Mesa ${mesaCodigo}` : "";
}