const OPERADORES_POR_CAMPO = {
  nivel: new Set(["igual", "mayor", "mayor_igual", "menor", "menor_igual"]),
  discapacidad: new Set(["igual"]),
};

document.querySelectorAll("[data-regla-sede-form]").forEach((formulario) => {
  const campo = formulario.querySelector('[name="campo"]');
  const operador = formulario.querySelector('[name="operador"]');
  const aplicarATodos = formulario.querySelector('[name="aplicar_a_todos"]');
  const alcances = Array.from(formulario.querySelectorAll('[name="alcances_especificos"]'));

  if (!campo || !operador) return;

  const actualizarOperadores = () => {
    const permitidos = OPERADORES_POR_CAMPO[campo.value]
      ?? new Set(["igual", "en"]);

    Array.from(operador.options).forEach((opcion) => {
      opcion.disabled = !permitidos.has(opcion.value);
      opcion.hidden = opcion.disabled;
    });

    if (!permitidos.has(operador.value)) operador.value = "igual";
  };

  campo.addEventListener("change", actualizarOperadores);
  actualizarOperadores();

  if (aplicarATodos && alcances.length) {
    const actualizarAlcances = (marcarTodos) => {
      alcances.forEach((opcion) => {
        opcion.checked = marcarTodos;
      });
    };

    const actualizarAplicarATodos = () => {
      aplicarATodos.checked = alcances.every((opcion) => opcion.checked);
    };

    aplicarATodos.addEventListener("change", () => actualizarAlcances(aplicarATodos.checked));
    alcances.forEach((opcion) => opcion.addEventListener("change", actualizarAplicarATodos));
    if (aplicarATodos.checked) actualizarAlcances(true);
    else actualizarAplicarATodos();
  }
});
