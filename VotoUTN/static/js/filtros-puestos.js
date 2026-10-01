document.querySelectorAll("[data-filtro-puesto]").forEach((grupo) => {
    const control = grupo.querySelector('input[type="checkbox"]');
    const opciones = grupo.querySelector("[data-opciones]");
    if (!control || !opciones) return;

    const actualizar = () => {
        opciones.hidden = !control.checked && opciones.dataset.tieneErrores !== "true";
    };

    control.addEventListener("change", actualizar);
    actualizar();
});
