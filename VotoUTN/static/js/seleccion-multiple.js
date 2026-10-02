document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-checkbox-group]").forEach((group) => {
    const master = group.querySelector("[data-select-all]");
    const options = Array.from(group.querySelectorAll("input[type='checkbox']:not([data-select-all])"));

    if (!master || options.length === 0) {
      return;
    }

    const actualizarMaster = () => {
      const seleccionadas = options.filter((option) => option.checked).length;
      master.checked = seleccionadas === options.length;
      master.indeterminate = seleccionadas > 0 && seleccionadas < options.length;
    };

    master.addEventListener("change", () => {
      options.forEach((option) => {
        option.checked = master.checked;
      });
      master.indeterminate = false;
    });

    options.forEach((option) => option.addEventListener("change", actualizarMaster));
    actualizarMaster();
  });
});
