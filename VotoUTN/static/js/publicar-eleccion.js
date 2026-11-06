const abrir = document.getElementById("abrir-publicacion");
const dialogo = document.getElementById("dialogo-publicacion");
const cancelar = document.getElementById("cancelar-publicacion");

if (abrir && dialogo && cancelar) {
  abrir.addEventListener("click", () => dialogo.showModal());
  cancelar.addEventListener("click", () => dialogo.close());
  dialogo.addEventListener("close", () => abrir.focus());
}
