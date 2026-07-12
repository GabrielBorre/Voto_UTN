const button = document.getElementById("startButton");

button.addEventListener("click", () => {

    button.disabled = true;

    button.innerHTML = "Iniciando...";

    setTimeout(() => {

        // Cuando exista la siguiente pantalla:
        // window.location.href = "escaneo.html";

        alert("Iría a la pantalla de escaneo.");

    }, 1200);

});