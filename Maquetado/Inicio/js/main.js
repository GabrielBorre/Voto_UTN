

console.log('Sistema de Gestión Electoral UTN.BA - Prototipo Página Inicial');

function mostrarConsulta() {
  const datos = {
    claustro: "Estudiantes",
    nombre: "Juan",
    apellido: "Pérez",
    dni: "12345678",
    sede: "Medrano",
    especialidad: "Ingeniería en Sistemas",
    mesa: "Mesa 12"
  };
  const cardReq = document.getElementById("card-request");
  cardReq.style.display = "none";

  const cardRes = document.getElementById("card-response");
  cardRes.style.display = "block";

  document.getElementById("resp-claustro").textContent = datos.claustro;
  document.getElementById("resp-nombre").textContent = datos.nombre;
  document.getElementById("resp-apellido").textContent = datos.apellido;
  document.getElementById("resp-dni").textContent = datos.dni;
  document.getElementById("resp-sede").textContent = datos.sede;
  document.getElementById("resp-especialidad").textContent = datos.especialidad;
  document.getElementById("resp-mesa").textContent = datos.mesa;
}


function ocultarConsulta() {  
  const cardReq = document.getElementById("card-request");
  cardReq.style.display = "block";

  const cardRes = document.getElementById("card-response");
  cardRes.style.display = "none";
  }
