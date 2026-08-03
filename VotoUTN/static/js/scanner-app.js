import { Camera } from "./camera.js";
import { PageQrScanner } from "./scanner.js";
import { submitManualAttendance, submitPage } from "./asistencia.js";
import {
    setCount,
    setStatus,
    setRegisterButtonLabel
} from "./ui.js";

const app = document.querySelector("#scanner-app");
const camera = new Camera(
    document.querySelector("#camera-video")
);

const AUTO_REGISTER_DELAY_MS = 3000;
const NEXT_PAGE_COOLDOWN_MS = 600;
const MESA_MISMATCH_STATUS_COOLDOWN_MS = 1200;

let autoRegisterTimerId = null;
let cameraStarted = false;
let isSubmitting = false;
let currentMesaNumber = null;
let mesaSessionNumber = null;
const mesaAccumulatedCodes = new Set();
let audioContext = null;
let lastMesaMismatchAt = 0;

const scanner = new PageQrScanner(
    camera.video,
    document.querySelector("#scan-canvas"),
    (code, count) => {
        if (mesaAccumulatedCodes.has(code)) {
            scanner.codes.delete(code);
            return;
        }

        const detectedMesaNumber = extractMesaFromCode(code);

        if (
            mesaSessionNumber &&
            detectedMesaNumber &&
            detectedMesaNumber !== mesaSessionNumber
        ) {
            scanner.codes.delete(code);

            const now = Date.now();
            if (now - lastMesaMismatchAt > MESA_MISMATCH_STATUS_COOLDOWN_MS) {
                setStatus(
                    `Mesa ${detectedMesaNumber} bloqueada. Registra primero la Mesa ${mesaSessionNumber}.`,
                    "error"
                );
                void playErrorTone();
                lastMesaMismatchAt = now;
            }

            return;
        }

        if (!currentMesaNumber || !mesaSessionNumber) {
            if (!currentMesaNumber && detectedMesaNumber) {
                currentMesaNumber = detectedMesaNumber;
            }

            if (!mesaSessionNumber && detectedMesaNumber) {
                mesaSessionNumber = detectedMesaNumber;
            }
        }

        const mesaVisibleCount = getProjectedUniqueMesaCount(scanner.codes);
        const mesaNumberForUi = currentMesaNumber || mesaSessionNumber;

        setCount(mesaVisibleCount);
        setRegisterButtonLabel(mesaNumberForUi, mesaVisibleCount);
        setRegisterButtonAvailability(mesaVisibleCount);

        restartAutoRegisterTimer();
        setStatus("Detectando codigos... manten la hoja estable.");
    },
    status => {
        setStatus(status);
    }
);

const registerButton = document.querySelector("#register-page");
const manualLoadButton = document.querySelector("#manual-load");
const resetSessionButton = document.querySelector("#reset-session");
const cameraPanel = document.querySelector("#camera-panel");
const scanControls = document.querySelector("#scan-controls");
const mesaSummaryView = document.querySelector("#mesa-summary-view");
const lastPageSummary = document.querySelector("#last-page-summary");

setCount(0);
setRegisterButtonLabel(null, 0);
registerButton.disabled = true;
hideMesaSummary();

function setRegisterButtonAvailability(totalCount) {
    if (!registerButton) {
        return;
    }

    registerButton.disabled = totalCount === 0;
}

function hideMesaSummary() {
    if (!mesaSummaryView) {
        return;
    }

    mesaSummaryView.classList.add("d-none");
    mesaSummaryView.setAttribute("aria-hidden", "true");

    if (lastPageSummary) {
        lastPageSummary.textContent = "";
    }
}

function showMesaSummary(mesaNumber, qrCount) {
    if (!mesaSummaryView || !lastPageSummary) {
        return;
    }

    const mesaText = mesaNumber ? `Mesa ${mesaNumber}` : "Mesa sin identificar";
    const qrLabel = qrCount === 1 ? "QR" : "QRs";

    lastPageSummary.textContent = `${mesaText}\n${qrCount} ${qrLabel} unicos acumulados`;
    mesaSummaryView.classList.remove("d-none");
    mesaSummaryView.setAttribute("aria-hidden", "false");
}

function enterMesaSummaryMode() {
    if (cameraPanel) {
        cameraPanel.classList.add("d-none");
    }

    if (scanControls) {
        scanControls.classList.add("d-none");
    }
}

function exitMesaSummaryMode() {
    if (cameraPanel) {
        cameraPanel.classList.remove("d-none");
    }

    if (scanControls) {
        scanControls.classList.remove("d-none");
    }

    hideMesaSummary();
}

function getProjectedUniqueMesaCount(pageCodesSet) {
    const projectedCodes = new Set(mesaAccumulatedCodes);
    for (const code of pageCodesSet) {
        projectedCodes.add(code);
    }

    return projectedCodes.size;
}

async function startCamera() {
    if (cameraStarted)
        return;

    try {
        setStatus("Iniciando camara...");
        await camera.start();
        scanner.start();
        cameraStarted = true;
        setStatus("Escanea la hoja completa del padron.");
    }
    catch (error) {
        setStatus(error.message, "error");
    }
}

function stopAutoRegisterTimer() {
    if (autoRegisterTimerId) {
        window.clearTimeout(autoRegisterTimerId);
        autoRegisterTimerId = null;
    }
}

function restartAutoRegisterTimer() {
    stopAutoRegisterTimer();

    if (scanner.codes.size === 0 || isSubmitting) {
        return;
    }

    autoRegisterTimerId = window.setTimeout(() => {
        registerCurrentPage("auto");
    }, AUTO_REGISTER_DELAY_MS);
}

function sleep(ms) {
    return new Promise(resolve => window.setTimeout(resolve, ms));
}

function getAudioContext() {
    if (audioContext) {
        return audioContext;
    }

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
        return null;
    }

    audioContext = new AudioContextClass();
    return audioContext;
}

async function beep({ frequency, durationMs, type }) {
    const ctx = getAudioContext();
    if (!ctx) {
        return;
    }

    if (ctx.state === "suspended") {
        try {
            await ctx.resume();
        } catch {
            return;
        }
    }

    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    oscillator.type = type;
    oscillator.frequency.value = frequency;
    gainNode.gain.value = 0.0001;

    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);

    const now = ctx.currentTime;
    gainNode.gain.exponentialRampToValueAtTime(0.14, now + 0.01);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + durationMs / 1000);

    oscillator.start(now);
    oscillator.stop(now + durationMs / 1000 + 0.02);
}

async function playSuccessTone() {
    await beep({ frequency: 920, durationMs: 110, type: "sine" });
    await beep({ frequency: 1260, durationMs: 130, type: "triangle" });
}

async function playErrorTone() {
    await beep({ frequency: 240, durationMs: 210, type: "sawtooth" });
}

function extractMesaFromCode(rawCode) {
    if (typeof rawCode !== "string") {
        return null;
    }

    try {
        const base64 = rawCode.trim().replace(/-/g, "+").replace(/_/g, "/");
        const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
        const binary = window.atob(padded);

        if (binary.length !== 12) {
            return null;
        }

        const data = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) {
            data[i] = binary.charCodeAt(i);
        }

        const mesa = (data[2] << 8) + data[3];
        return Number.isFinite(mesa) && mesa > 0 ? mesa : null;
    } catch {
        return null;
    }
}

function clearCurrentPageState() {
    scanner.clear();
    currentMesaNumber = null;
    mesaSessionNumber = null;
    lastMesaMismatchAt = 0;
    mesaAccumulatedCodes.clear();
    setCount(0);
    setRegisterButtonLabel(null, 0);
    setRegisterButtonAvailability(0);
}

function clearCurrentPageScanOnly() {
    scanner.clear();
    currentMesaNumber = null;
    const accumulatedCount = mesaAccumulatedCodes.size;
    setCount(accumulatedCount);
    setRegisterButtonLabel(mesaSessionNumber, accumulatedCount);
    setRegisterButtonAvailability(accumulatedCount);
}

async function finalizeMesaSession(mesaNumber, accumulatedUniqueCount) {
    enterMesaSummaryMode();
    showMesaSummary(mesaNumber, accumulatedUniqueCount);
    clearCurrentPageState();

}

async function registerCurrentPage(origin) {
    if (isSubmitting) {
        return;
    }

    const projectedTotalForMesa = getProjectedUniqueMesaCount(scanner.codes);

    if (projectedTotalForMesa === 0) {
        setStatus("Esperando deteccion de al menos un QR.");
        return;
    }

    if (origin === "manual" && scanner.codes.size === 0) {
        stopAutoRegisterTimer();
        scanner.stop();
        void playSuccessTone();
        await finalizeMesaSession(mesaSessionNumber, mesaAccumulatedCodes.size);
        return;
    }

    const detectedCount = scanner.codes.size;
    const mesaForSummary = currentMesaNumber || mesaSessionNumber;

    isSubmitting = true;
    stopAutoRegisterTimer();

    scanner.stop();
    setStatus("Registrando hoja...", "info");

    try {
        const result = await submitPage(
            app.dataset.apiUrl,
            scanner.codes
        );

        setStatus(
            `Hoja registrada (${detectedCount} QR). Podes pasar a la siguiente.`,
            "success"
        );
        void playSuccessTone();

        for (const code of scanner.codes) {
            mesaAccumulatedCodes.add(code);
        }

        const accumulatedUniqueCount = mesaAccumulatedCodes.size;

        if (origin === "manual") {
            await finalizeMesaSession(mesaForSummary, accumulatedUniqueCount);
            return;
        }

        clearCurrentPageScanOnly();

        await sleep(NEXT_PAGE_COOLDOWN_MS);
        scanner.start();

        if (origin === "manual") {
            setStatus("Escaneo continuo activo.", "info");
        }
    }
    catch (error) {
        setStatus(error.message, "error");
        void playErrorTone();
        if (origin === "manual") {
            exitMesaSummaryMode();
        }
        scanner.start();

        const mesaVisibleCount = getProjectedUniqueMesaCount(scanner.codes);
        setCount(mesaVisibleCount);
        setRegisterButtonLabel(currentMesaNumber || mesaSessionNumber, mesaVisibleCount);
        restartAutoRegisterTimer();
    }
    finally {
        isSubmitting = false;
    }
}

function resetSession() {
    stopAutoRegisterTimer();
    exitMesaSummaryMode();
    clearCurrentPageState();
    setStatus("Escanea la primera hoja de la nueva mesa.");

    if (cameraStarted) {
        scanner.start();
    } else {
        void startCamera();
    }
}

function stopAll() {
    stopAutoRegisterTimer();
    scanner.stop();
    camera.stop();
    cameraStarted = false;
}

registerButton.addEventListener("click", () => {
    registerCurrentPage("manual");
});

manualLoadButton.addEventListener("click", () => {
    const mesaInput = window.prompt("Ingresá el número de mesa del elector:");

    if (mesaInput === null) {
        return;
    }

    const mesaNumero = Number.parseInt(mesaInput.trim(), 10);
    if (!Number.isInteger(mesaNumero) || mesaNumero <= 0) {
        setStatus("Ingresá un número de mesa válido.", "error");
        void playErrorTone();
        return;
    }

    const legajoInput = window.prompt("Ingresá el legajo del elector:");

    if (legajoInput === null) {
        return;
    }

    const legajo = legajoInput.trim();
    if (!legajo) {
        setStatus("Ingresá un legajo válido.", "error");
        void playErrorTone();
        return;
    }

    void (async () => {
        try {
            setStatus(`Registrando manualmente al legajo ${legajo} en mesa ${mesaNumero}...`, "info");

            const result = await submitManualAttendance(app.dataset.apiUrl, mesaNumero, legajo);

            if (result.invalidos?.length) {
                setStatus(`No se encontró al elector ${legajo} en la mesa ${mesaNumero}.`, "error");
                void playErrorTone();
                return;
            }

            if (result.creados?.length) {
                setStatus(`Elector ${legajo} registrado manualmente en la mesa ${mesaNumero}.`, "success");
                void playSuccessTone();
                return;
            }

            if (result.ya_registrados?.length) {
                setStatus(`El elector ${legajo} ya estaba registrado en la mesa ${mesaNumero}.`, "info");
                return;
            }

            setStatus("No se pudo completar la carga manual.", "error");
            void playErrorTone();
        } catch (error) {
            setStatus(error.message, "error");
            void playErrorTone();
        }
    })();
});

resetSessionButton.addEventListener("click", resetSession);

void startCamera();

document.addEventListener(
    "visibilitychange",
    () => {
        if (document.hidden) {
            stopAll();
        } else {
            void startCamera();
        }
    }
);

window.addEventListener(
    "pagehide",
    () => {
        stopAll();
    }
);

window.addEventListener(
    "beforeunload",
    () => {
        stopAll();
    }
);
