import { Camera } from "./camera.js";
import { PageQrScanner } from "./scanner.js";
import { submitPage } from "./attendance.js";
import {
    setCount,
    setStatus,
    showResult,
    hideResult
} from "./ui.js";
const app = document.querySelector("#scanner-app");
const camera = new Camera(
    document.querySelector("#camera-video")
);
const scanner = new PageQrScanner(
    camera.video,
    document.querySelector("#scan-canvas"),
    (_, count) => {
        setCount(count);
    },
    status => {
        setStatus(status);
    }
);
const startButton = document.querySelector("#start-camera");
const nextButton = document.querySelector("#next-page");
let cameraStarted = false;
async function startCamera() {
    if (cameraStarted)
        return;
    try {
        setStatus("Iniciando cámara...");
        await camera.start();
        scanner.start();
        cameraStarted = true;
        startButton.classList.add("d-none");
        setStatus(
            "Escaneá la hoja completa del padrón"
        );
    }
    catch (error) {
        setStatus(error.message);
    }
}
startButton.addEventListener(
    "click",
    startCamera
);
nextButton.addEventListener(
    "click",
    registerPage
);
async function registerPage() {
    if (scanner.codes.size === 0) {
        setStatus(
            "Todavía no se detectó ningún QR."
        );
        return;
    }
    nextButton.disabled = true;
    // Congela la lectura mientras se confirma la hoja actual.
    scanner.stop();
    setStatus(
        "Registrando asistencia..."
    );
    try {
        const result = await submitPage(
            app.dataset.apiUrl,
            scanner.codes
        );
        showResult(
            result,
            nextPage,
            finishScanning
        );
    }
    catch (error) {
        setStatus(error.message);
        nextButton.disabled = false;
        scanner.start();
    }
}
function nextPage() {
    scanner.clear();
    setCount(0);
    hideResult();
    nextButton.disabled = false;
    scanner.start();
    setStatus(
        "Escaneá la siguiente página"
    );
}
function finishScanning() {
    scanner.stop();
    camera.stop();
    window.location.assign(
        app.dataset.listUrl
    );
}
document.addEventListener(
    "visibilitychange",
    () => {
        if (document.hidden) {
            scanner.stop();
            camera.stop();
            cameraStarted = false;
        }
    }
);
window.addEventListener(
    "pagehide",
    () => {
        scanner.stop();
        camera.stop();
    }
);
window.addEventListener(
    "beforeunload",
    () => {
        scanner.stop();
        camera.stop();
    }
);
