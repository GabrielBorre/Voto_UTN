const formulario = document.getElementById("formulario-editar-plazo-justificativos");
const botonAbrir = document.getElementById("abrir-dialogo-editar-plazo");
const dialogo = document.getElementById("dialogo-editar-plazo-justificativos");
const botonCancelar = document.getElementById("cancelar-dialogo-editar-plazo");
const fecha = document.getElementById("id_fecha_limite_justificacion_electores");
const fechaConfirmacion = document.getElementById("nueva-fecha-limite-justificativos");

function mostrarFechaConfirmacion() {
  if (!fecha.value) {
    fechaConfirmacion.textContent = "";
    return;
  }
  const [anio, mes, dia] = fecha.value.split("-");
  fechaConfirmacion.textContent = `${dia}/${mes}/${anio}`;
}

if (formulario && botonAbrir && dialogo && botonCancelar && fecha && fechaConfirmacion) {
  botonAbrir.addEventListener("click", () => {
    if (!formulario.reportValidity()) return;
    mostrarFechaConfirmacion();
    dialogo.showModal();
  });
  fecha.addEventListener("change", mostrarFechaConfirmacion);
  botonCancelar.addEventListener("click", () => dialogo.close());
}
