export function setStatus(text) { document.querySelector('#camera-status').textContent = text; }
export function setCount(count) { document.querySelector('#qr-count').textContent = `${count} QR escaneados`; document.querySelector('#next-page').disabled = count === 0; }
export function showResult({ registered, already_registered, invalid = [] }, onContinue, onExit) {
  const panel = document.querySelector('#result-panel');
  const invalidMessage = invalid.length ? `<p class="text-danger small mb-4">${invalid.length} QR no pertenece(n) al padron.</p>` : '<div class="mb-4"></div>';
  panel.innerHTML = `<article class="result-card card border-0 shadow"><div class="card-body text-center p-4"><div class="display-5 text-success mb-2">OK</div><h1 class="h4">Pagina registrada</h1><p class="mb-1"><strong>${registered.length}</strong> asistencias nuevas</p><p class="text-muted small mb-1">${already_registered.length} ya estaban registradas.</p>${invalidMessage}<button class="btn btn-primary btn-lg w-100 mb-2" id="continue-scan">Escanear siguiente pagina</button><button class="btn btn-outline-secondary w-100" id="finish-scan">Finalizar</button></div></article>`;
  panel.classList.remove('d-none'); document.querySelector('#continue-scan').onclick = onContinue; document.querySelector('#finish-scan').onclick = onExit;
}
export function hideResult() { document.querySelector('#result-panel').classList.add('d-none'); }
