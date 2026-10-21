const botonAbrir = document.getElementById("abrir-dialogo-limite-mesas");
const dialogo = document.getElementById("dialogo-limite-mesas");
const formularioDialogo = document.getElementById("formulario-dialogo-limite-mesas");
const formularioResolucion = document.getElementById("formulario-aprobar-con-limite-mesas");
const entradaMaximo = document.getElementById("cantidad-maxima-mesas-nuevas");
const maximoOculto = document.getElementById("maximo_mesas_nuevas");
const botonCancelar = document.getElementById("cancelar-dialogo-limite-mesas");

if (
  botonAbrir &&
  dialogo &&
  formularioDialogo &&
  formularioResolucion &&
  entradaMaximo &&
  maximoOculto &&
  botonCancelar
) {
  botonAbrir.addEventListener("click", () => {
    dialogo.showModal();
    entradaMaximo.focus();
  });

  botonCancelar.addEventListener("click", () => {
    dialogo.close();
  });

  entradaMaximo.addEventListener("input", () => {
    entradaMaximo.setCustomValidity("");
  });

  formularioDialogo.addEventListener("submit", (evento) => {
    evento.preventDefault();
    if (!entradaMaximo.value || !entradaMaximo.checkValidity()) {
      entradaMaximo.reportValidity();
      return;
    }

    const maximo = Number(entradaMaximo.value);
    if (!Number.isInteger(maximo) || maximo < 0) {
      entradaMaximo.setCustomValidity("Ingresá un número entero mayor o igual a cero.");
      entradaMaximo.reportValidity();
      return;
    }

    maximoOculto.value = String(maximo);
    dialogo.close();
    formularioResolucion.requestSubmit();
  });
}
