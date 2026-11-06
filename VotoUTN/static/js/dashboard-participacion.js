const consultaEscritorio = window.matchMedia("(min-width: 768px)");

document.querySelectorAll("[data-autoenviar]").forEach((selector) => {
  selector.addEventListener("change", () => selector.form.requestSubmit());
});

function prepararRegistroManualMesas() {
  const dialogo = document.getElementById("dialogo-registrar-mesa");
  if (!dialogo) return;
  const formulario = document.getElementById("formulario-registrar-mesa");
  const cancelar = document.getElementById("cancelar-registrar-mesa");
  const campos = {
    codigo: dialogo.querySelector("[data-registrar-codigo]"),
    electores: dialogo.querySelector("[data-registrar-electores]"),
    inasistencias: dialogo.querySelector("[data-registrar-inasistencias]"),
  };

  document.querySelectorAll("[data-registrar-mesa]").forEach((boton) => {
    boton.addEventListener("click", () => {
      formulario.action = boton.dataset.accion;
      campos.codigo.textContent = boton.dataset.codigo;
      campos.electores.textContent = boton.dataset.electores;
      campos.inasistencias.textContent = boton.dataset.inasistencias;
      dialogo.showModal();
    });
  });
  cancelar.addEventListener("click", () => dialogo.close());
  formulario.addEventListener("submit", () => {
    formulario.querySelector("button[type='submit']").disabled = true;
  });
}

prepararRegistroManualMesas();

function dibujarHistorial() {
  const lienzo = document.getElementById("grafico-historial");
  const datos = document.getElementById("historial-datos");
  if (!lienzo || !datos || !consultaEscritorio.matches) return;

  if (!window.Chart) {
    const aviso = document.getElementById("grafico-historial-aviso");
    aviso.textContent = "No se pudo cargar el gráfico.";
    aviso.hidden = false;
    return;
  }

  const { etiquetas, porcentajes, participaron, totales } = JSON.parse(datos.textContent);
  new window.Chart(lienzo, {
    type: "line",
    data: {
      labels: etiquetas,
      datasets: [
        {
          label: "Participación (%)",
          data: porcentajes,
          borderColor: "#1557b0",
          backgroundColor: "rgba(21, 87, 176, .15)",
          pointBackgroundColor: "#0b3d91",
          pointRadius: 5,
          fill: true,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (valor) => `${valor}%` } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => `${item.parsed.y}% (${participaron[item.dataIndex]} de ${totales[item.dataIndex]} electores)`,
          },
        },
      },
    },
  });
}

dibujarHistorial();
