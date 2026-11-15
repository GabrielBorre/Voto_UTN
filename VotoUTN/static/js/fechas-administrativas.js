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

const formularioCambioSede = document.getElementById("formulario-editar-plazo-cambio-sede");
const botonAbrirCambioSede = document.getElementById("abrir-dialogo-editar-plazo-cambio-sede");
const dialogoCambioSede = document.getElementById("dialogo-editar-plazo-cambio-sede");
const botonCancelarCambioSede = document.getElementById("cancelar-dialogo-editar-plazo-cambio-sede");
const fechaCambioSede = document.getElementById("id_fecha_cierre_solicitudes_cambio_sede");
const fechaConfirmacionCambioSede = document.getElementById("nueva-fecha-limite-cambio-sede");

function mostrarFechaCambioSede() {
  if (!fechaCambioSede.value) {
  fechaConfirmacionCambioSede.textContent = "";
  return;
  }
  const [anio, mes, dia] = fechaCambioSede.value.split("-");
  fechaConfirmacionCambioSede.textContent = `${dia}/${mes}/${anio}`;
}

if (
  formularioCambioSede
  && botonAbrirCambioSede
  && dialogoCambioSede
  && botonCancelarCambioSede
  && fechaCambioSede
  && fechaConfirmacionCambioSede
) {
  botonAbrirCambioSede.addEventListener("click", () => {
  if (!formularioCambioSede.reportValidity()) return;
  mostrarFechaCambioSede();
  dialogoCambioSede.showModal();
  });
  fechaCambioSede.addEventListener("change", mostrarFechaCambioSede);
  botonCancelarCambioSede.addEventListener("click", () => dialogoCambioSede.close());
}

const formularioEximicion = document.getElementById("formulario-editar-plazo-eximicion");
const botonAbrirEximicion = document.getElementById("abrir-dialogo-editar-plazo-eximicion");
const dialogoEximicion = document.getElementById("dialogo-editar-plazo-eximicion");
const botonCancelarEximicion = document.getElementById("cancelar-dialogo-editar-plazo-eximicion");
const fechaEximicion = document.getElementById("id_fecha_limite_justificacion_autoridades");
const fechaConfirmacionEximicion = document.getElementById("nueva-fecha-limite-eximicion");

function mostrarFechaEximicion() {
  if (!fechaEximicion.value) {
    fechaConfirmacionEximicion.textContent = "";
    return;
  }
  const [anio, mes, dia] = fechaEximicion.value.split("-");
  fechaConfirmacionEximicion.textContent = `${dia}/${mes}/${anio}`;
}

if (
  formularioEximicion
  && botonAbrirEximicion
  && dialogoEximicion
  && botonCancelarEximicion
  && fechaEximicion
  && fechaConfirmacionEximicion
) {
  botonAbrirEximicion.addEventListener("click", () => {
    if (!formularioEximicion.reportValidity()) return;
    mostrarFechaEximicion();
    dialogoEximicion.showModal();
  });
  fechaEximicion.addEventListener("change", mostrarFechaEximicion);
  botonCancelarEximicion.addEventListener("click", () => dialogoEximicion.close());
}
