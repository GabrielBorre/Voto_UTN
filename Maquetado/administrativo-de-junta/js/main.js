// main.js
// Archivo reservado para futuras interacciones del maquetado:
// - validaciones de formularios
// - navegación dinámica
// - filtros de elecciones
// - cambio de estados visuales

console.log('Sistema de Gestión Electoral UTN.BA - Prototipo Administrativo de Junta');

function abrirModal() {
  document.getElementById("modal-rechazo").style.display = "flex";
}

function cerrarModal() {
  document.getElementById("modal-rechazo").style.display = "none";
}

function confirmarRechazo() {
  const motivo = document.getElementById("motivo-rechazo").value.trim();
  if (!motivo) {
    alert("Debe ingresar un motivo antes de confirmar.");
    return;
  }
  // Aquí podés enviar el motivo al servidor o guardarlo
  alert("Solicitud rechazada con motivo: " + motivo);
  cerrarModal();
}


function mostrarTab(event, tab) {
  event.preventDefault(); // evita que el enlace haga scroll arriba

  document.getElementById("tab-autoridad").style.display = tab === "autoridad" ? "block" : "none";
  document.getElementById("tab-elector").style.display = tab === "elector" ? "block" : "none";

  // actualizar estado activo en las pestañas
  const links = document.querySelectorAll(".nav a");
  links.forEach(link => link.classList.remove("active"));
  event.target.classList.add("active");
}





const inputMesa = document.getElementById("mesa");
const inputBusqueda = document.getElementById("busqueda");
const filas = document.querySelectorAll("#lista tbody tr");

// Normaliza texto: quita acentos y pasa a minúsculas
function normalizar(texto) {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function filtrar() {
  const mesa = inputMesa.value.trim();
  const texto = inputBusqueda.value.trim();

  filas.forEach(fila => {
    const [nombre, dni, legajo, mesaFila] = Array.from(fila.children).map(td => td.textContent);

    // Coincidencia exacta para mesa
    const coincideMesa = mesa === "" || mesaFila === mesa;

    // Coincidencia "empieza con" para DNI o Legajo
    const coincideNumero = texto !== "" && (dni.startsWith(texto) || legajo.startsWith(texto));

    // Coincidencia flexible para nombre (ignora mayúsculas y acentos)
    const coincideNombre = texto !== "" && normalizar(nombre).includes(normalizar(texto));

    // Si no hay texto, mostrar todo lo de la mesa
    const coincideTexto = texto === "" || coincideNumero || coincideNombre;

    fila.style.display = (coincideMesa && coincideTexto) ? "" : "none";
  });
}

inputMesa.addEventListener("input", filtrar);
inputBusqueda.addEventListener("input", filtrar);




// Delegación de eventos: escucha todos los botones con clase .registrar
document.addEventListener("click", function (e) {
  if (e.target.classList.contains("registrar")) {
    const fila = e.target.closest("tr");
    const nombre = fila.children[0].textContent;
    const dni = fila.children[1].textContent;

    const confirmar = confirm(`¿Registrar inasistencia de ${nombre} (DNI: ${dni})?`);
    if (confirmar) {
      // Aquí podés enviar la info al servidor o marcar visualmente
      fila.style.backgroundColor = "#f8d7da"; // rojo claro para indicar inasistencia
      e.target.disabled = true;
      e.target.textContent = "Inasistencia registrada";
    }
  }
});
