document.querySelectorAll("[data-autoguardar-configuracion]").forEach((formulario) => {
  const estado = formulario.querySelector("[data-autosave-status]");
  const controles = Array.from(formulario.querySelectorAll("input, select, textarea"))
    .filter((control) => control.name !== "csrfmiddlewaretoken");

  let cambiosPendientes = false;
  let revision = 0;
  let temporizador = null;
  let guardadoEnCurso = null;

  const programarGuardadoAutomatico = (demora) => {
    window.clearTimeout(temporizador);
    temporizador = window.setTimeout(() => {
      temporizador = null;
      guardar();
    }, demora);
  };

  const prepararDatos = () => {
    const datos = new FormData(formulario);
    datos.set("guardar-configuracion", "1");
    datos.set("autoguardado", "1");
    return datos;
  };

  const guardar = () => {
    if (guardadoEnCurso) {
      return guardadoEnCurso.then((guardado) => guardado && cambiosPendientes ? guardar() : guardado);
    }
    if (!cambiosPendientes) return Promise.resolve(true);
    if (!formulario.reportValidity()) return Promise.resolve(false);

    const revisionEnviada = revision;
    estado.textContent = "Guardando…";
    guardadoEnCurso = fetch(formulario.action || window.location.href, {
      method: "POST",
      body: prepararDatos(),
      credentials: "same-origin",
      keepalive: true,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(async (respuesta) => {
        if (!respuesta.ok) throw new Error("No se pudo guardar la configuración.");
        const contenido = await respuesta.json().catch(() => ({}));
        if (revision === revisionEnviada) {
          cambiosPendientes = false;
          estado.textContent = contenido.mensaje || "Configuración guardada automáticamente.";
        } else {
          estado.textContent = "Guardando los últimos cambios…";
        }
        return true;
      })
      .catch(() => {
        estado.textContent = "No se pudo guardar. Revisá los valores e intentá de nuevo.";
        return false;
      })
      .finally(() => {
        guardadoEnCurso = null;
        if (cambiosPendientes && !temporizador) {
          temporizador = window.setTimeout(() => {
            temporizador = null;
            guardar();
          }, 100);
        }
      });

    return guardadoEnCurso;
  };

  const programarGuardado = () => {
    revision += 1;
    cambiosPendientes = true;
    estado.textContent = "Hay cambios pendientes de guardar…";
    programarGuardadoAutomatico(450);
  };

  controles.forEach((control) => {
    control.addEventListener("input", programarGuardado);
    control.addEventListener("change", programarGuardado);
  });

  formulario.addEventListener("submit", () => {
    window.clearTimeout(temporizador);
    temporizador = null;
    cambiosPendientes = false;
    estado.textContent = "Guardando configuración…";
  });

  document.addEventListener("click", (evento) => {
    const enlace = evento.target.closest("a[href]");
    if (!enlace || enlace.target || !cambiosPendientes) return;

    const destino = new URL(enlace.href, window.location.href);
    if (destino.origin !== window.location.origin) return;

    evento.preventDefault();
    window.clearTimeout(temporizador);
    temporizador = null;
    guardar().then((guardado) => {
      if (guardado || window.confirm("No se pudieron guardar los cambios. ¿Querés salir igualmente?")) {
        window.location.assign(destino.href);
      }
    });
  });

  window.addEventListener("pagehide", () => {
    if (!cambiosPendientes || guardadoEnCurso || !navigator.sendBeacon) return;
    navigator.sendBeacon(formulario.action || window.location.href, prepararDatos());
  });
});
