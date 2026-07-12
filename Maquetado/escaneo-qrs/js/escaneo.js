
const totalPages = 18;

let currentPage = 1;

const statusBox = document.getElementById("statusBox");
const statusTitle = document.getElementById("statusTitle");
const statusText = document.getElementById("statusText");

const page = document.getElementById("currentPage");

const progress = document.getElementById("progressBar");

function updateProgress(){

    page.innerText = currentPage;

    progress.style.width = ((currentPage/totalPages)*100)+"%";

}

function scanPage(){

    statusTitle.innerHTML="Analizando página...";

    statusText.innerHTML="Detectando códigos QR.";

    setTimeout(()=>{

        statusBox.classList.remove("waiting");
        statusBox.classList.add("success");

        statusTitle.innerHTML="✓ Página registrada";

        statusText.innerHTML="Puede pasar a la siguiente hoja.";

        setTimeout(()=>{

            currentPage++;

            if(currentPage>totalPages){

                // Cuando exista la siguiente pantalla
                // window.location="procesando.html";

                alert("Iría a Procesando");

                return;

            }

            updateProgress();

            statusBox.classList.remove("success");
            statusBox.classList.add("waiting");

            statusTitle.innerHTML="Listo para escanear";

            statusText.innerHTML="Mantenga la hoja estable.";

            scanPage();

        },1800);

    },2200);

}

updateProgress();

setTimeout(scanPage,1800);