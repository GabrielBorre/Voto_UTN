const formulario = document.getElementById("consulta-form");
const estado = document.getElementById("consulta-estado");
const botonConsulta = formulario.querySelector('button[type="submit"]');

function mostrarConsulta(datos) {
  Object.entries(datos).forEach(([campo, valor]) => {
    const destino = document.getElementById(`resp-${campo}`);
    if (destino) destino.textContent = valor ?? "";
  });

  document.getElementById("card-request").hidden = true;
  document.getElementById("card-response").hidden = false;
}

function ocultarConsulta() {
  document.getElementById("card-request").hidden = false;
  document.getElementById("card-response").hidden = true;
  estado.textContent = "";
  document.getElementById("codigo").focus();
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const codigo = document.getElementById("codigo").value.trim();
  if (!codigo) return;

  estado.textContent = "Consultando padrón...";
  estado.classList.remove("is-error");
  botonConsulta.disabled = true;

  try {
    const respuesta = await fetch(formulario.dataset.apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo })
    });
    const datos = await respuesta.json();

    if (!respuesta.ok) {
      const detalle = datos.detail || Object.values(datos).flat()[0];
      throw new Error(detalle || "No se pudo realizar la consulta.");
    }

    mostrarConsulta(datos);
    estado.textContent = "";
  } catch (error) {
    estado.textContent = error.message || "No se pudo conectar con el servicio. Intentá nuevamente.";
    estado.classList.add("is-error");
  } finally {
    botonConsulta.disabled = false;
  }
});

document.getElementById("volver-consulta").addEventListener("click", ocultarConsulta);