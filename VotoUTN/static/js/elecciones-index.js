console.log("Sistema de Gestion Electoral UTN.BA - Pagina inicial");

const datosConsulta = {
  claustro: "Estudiantes",
  nombre: "Juan",
  apellido: "Perez",
  dni: "12345678",
  sede: "Medrano",
  especialidad: "Ingenieria en Sistemas",
  mesa: "Mesa 12"
};

function mostrarConsulta() {
  document.getElementById("card-request").hidden = true;
  document.getElementById("card-response").hidden = false;

  Object.entries(datosConsulta).forEach(([campo, valor]) => {
    document.getElementById(`resp-${campo}`).textContent = valor;
  });
}

function ocultarConsulta() {
  document.getElementById("card-request").hidden = false;
  document.getElementById("card-response").hidden = true;
  document.getElementById("codigo").focus();
}

document.getElementById("consulta-form").addEventListener("submit", (evento) => {
  evento.preventDefault();
  mostrarConsulta();
});

document.getElementById("volver-consulta").addEventListener("click", ocultarConsulta);