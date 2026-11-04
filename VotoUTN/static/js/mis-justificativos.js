const casillaReclamo = document.querySelector('input[type="checkbox"]#id_reclamo_participacion');

if (casillaReclamo) {
  const contenedor = (nombre) => document.querySelector(`[data-campo-justificativo="${nombre}"]`);
  const ocultosEnReclamo = ["ausencia", "tipo"].map(contenedor).filter(Boolean);
  const visiblesEnReclamo = ["comprobante_extraviado"].map(contenedor).filter(Boolean);

  const actualizar = () => {
    const esReclamo = casillaReclamo.checked;
    ocultosEnReclamo.forEach((campo) => {
      campo.hidden = esReclamo;
      campo.querySelectorAll("select, input").forEach((control) => {
        control.disabled = esReclamo;
        control.required = !esReclamo;
      });
    });
    visiblesEnReclamo.forEach((campo) => {
      campo.hidden = !esReclamo;
      campo.querySelectorAll("input").forEach((control) => {
        control.disabled = !esReclamo;
        if (!esReclamo) control.checked = false;
      });
    });
  };

  casillaReclamo.addEventListener("change", actualizar);
  actualizar();
}
