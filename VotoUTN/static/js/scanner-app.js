import { Camera } from "./camera.js";
import { PageQrScanner } from "./scanner.js";
import { gestionarMesa, submitManualAttendance, submitPage } from "./asistencia.js";
import {
    setCount,
    setStatus,
    setRegisterButtonLabel
} from "./ui.js";

const app = document.querySelector("#scanner-app");
const esDispositivoMovil = window.matchMedia("(max-width: 767.98px)").matches;
const camera = new Camera(
    document.querySelector("#camera-video")
);

const AUTO_REGISTER_DELAY_MS = 3000;
const NEXT_PAGE_COOLDOWN_MS = 600;
const NOTICE_COOLDOWN_MS = 1200;

/* Fases: select (pide QR o codigo de mesa) -> info (datos de la mesa) -> scanning (electores) -> summary */
let phase = "select";
let autoRegisterTimerId = null;
let cameraStarted = false;
let isSubmitting = false;
let isQueryingMesa = false;
let mesaActual = null;
let mesaPendiente = null;
let mesaBaseRegistrados = 0;
const mesaAccumulatedCodes = new Set();
let audioContext = null;
let lastNoticeAt = 0;

const expectedElectionId = (() => {
    try {
        const apiUrl = app?.dataset?.apiUrl || "";
        const match = apiUrl.match(/\/elecciones?\/(\d+)\//i);
        if (!match) {
            return null;
        }
        const electionId = Number.parseInt(match[1], 10);
        return Number.isInteger(electionId) && electionId > 0 ? electionId : null;
    }
    catch {
        return null;
    }
})();

/* Formatos: elector V1.EEMMIIIIIIIIFFFF, mesa M1.EEMMFFFF (base36/base36/alfanum/firma). Solo se usa para guiar la UI. */
function parseQr(rawCode) {
    if (typeof rawCode !== "string") {
        return null;
    }

    const [version, contenido] = rawCode.trim().toUpperCase().split(".");
    if (!contenido || !/^[A-Z0-9]+$/.test(contenido)) {
        return null;
    }

    let tipo = null;
    if (version === "V1" && contenido.length >= 6) {
        tipo = "elector";
    } else if (version === "M1" && contenido.length === 8) {
        tipo = "mesa";
    }
    if (!tipo) {
        return null;
    }

    const eleccionId = Number.parseInt(contenido.slice(0, 2), 36);
    const mesaNumero = Number.parseInt(contenido.slice(2, 4), 36);
    return {
        tipo,
        eleccionId: Number.isFinite(eleccionId) && eleccionId > 0 ? eleccionId : null,
        mesaNumero: Number.isFinite(mesaNumero) && mesaNumero > 0 ? mesaNumero : null
    };
}

function noticeAllowed() {
    const now = Date.now();
    if (now - lastNoticeAt > NOTICE_COOLDOWN_MS) {
        lastNoticeAt = now;
        return true;
    }
    return false;
}

function notifyError(message) {
    if (!noticeAllowed()) {
        return;
    }
    setStatus(message, "error");
    void playErrorTone();
}

const scanner = new PageQrScanner(
    camera.video,
    document.querySelector("#scan-canvas"),
    (code) => {
        const parsed = parseQr(code);

        if (phase !== "select" && phase !== "scanning") {
            scanner.codes.delete(code);
            return;
        }

        if (phase === "select") {
            scanner.codes.delete(code);
            if (!parsed) {
                notifyError("QR no reconocido. Escaneá el QR de la mesa.");
            } else if (parsed.tipo !== "mesa") {
                notifyError("Primero escaneá el QR de la mesa que vas a registrar.");
            } else if (expectedElectionId && parsed.eleccionId && parsed.eleccionId !== expectedElectionId) {
                notifyError(`QR de otra elección (ID ${parsed.eleccionId}). Escaneá solo la elección ${expectedElectionId}.`);
            } else if (!isQueryingMesa) {
                void consultarMesa({ codigo_qr: code });
            }
            return;
        }

        if (mesaAccumulatedCodes.has(code)) {
            scanner.codes.delete(code);
            return;
        }

        if (!parsed) {
            scanner.codes.delete(code);
            return;
        }

        if (parsed.tipo === "mesa") {
            scanner.codes.delete(code);
            if (parsed.mesaNumero !== mesaActual.numero) {
                notifyError(`Primero registrá la mesa ${mesaActual.codigo} con el botón antes de escanear otra mesa.`);
            }
            return;
        }

        if (expectedElectionId && parsed.eleccionId && parsed.eleccionId !== expectedElectionId) {
            scanner.codes.delete(code);
            notifyError(`QR de otra elección (ID ${parsed.eleccionId}). Escaneá solo la elección ${expectedElectionId}.`);
            return;
        }

        if (parsed.mesaNumero && parsed.mesaNumero !== mesaActual.numero) {
            scanner.codes.delete(code);
            notifyError(`El QR es de la mesa ${parsed.mesaNumero}. Registrá primero la mesa ${mesaActual.codigo}.`);
            return;
        }

        const mesaVisibleCount = getProjectedUniqueMesaCount(scanner.codes);
        setCount(mesaVisibleCount);
        setRegisterButtonLabel(mesaActual.codigo, mesaVisibleCount);

        restartAutoRegisterTimer();
        setStatus("Detectando codigos... manten la hoja estable.");
    },
    status => {
        if (phase === "scanning") {
            setStatus(status);
        }
    }
);

const registerButton = document.querySelector("#register-page");
const manualLoadButtons = document.querySelectorAll(".js-manual-load");
const resetSessionButton = document.querySelector("#reset-session");
const cameraPanel = document.querySelector("#camera-panel");
const scanControls = document.querySelector("#scan-controls");
const mesaSummaryView = document.querySelector("#mesa-summary-view");
const lastPageSummary = document.querySelector("#last-page-summary");
const mesaSelectControls = document.querySelector("#mesa-select-controls");
const mesaCodeForm = document.querySelector("#mesa-code-form");
const mesaCodeInput = document.querySelector("#mesa-code-input");
const mesaInfoView = document.querySelector("#mesa-info-view");
const mesaInfoCodigo = document.querySelector("#mesa-info-codigo");
const mesaInfoDetalle = document.querySelector("#mesa-info-detalle");
const mesaInfoMensaje = document.querySelector("#mesa-info-mensaje");
const mesaInfoControls = document.querySelector("#mesa-info-controls");
const mesaStartButton = document.querySelector("#mesa-start");
const mesaChangeButton = document.querySelector("#mesa-change");
const manualDesktopForm = document.querySelector("#manual-desktop-form");
const manualDesktopStatus = document.querySelector("#manual-desktop-status");
const manualDniPanel = document.querySelector("#manual-dni-panel");
const manualDniForm = document.querySelector("#manual-dni-form");
const manualDniInput = document.querySelector("#manual-dni-input");
const manualDniMesa = document.querySelector("#manual-dni-mesa");
const manualDniError = document.querySelector("#manual-dni-error");
const manualDniCancel = document.querySelector("#manual-dni-cancel");
const confirmPanel = document.querySelector("#confirm-panel");
const confirmText = document.querySelector("#confirm-text");
const confirmAccept = document.querySelector("#confirm-accept");
const confirmCancel = document.querySelector("#confirm-cancel");

/* Dialogos renderizados en la pagina; la camara se pausa mientras estan abiertos. */
function openManualDniDialog() {
    stopAutoRegisterTimer();
    scanner.stop();
    manualDniMesa.textContent = `Mesa ${mesaActual.codigo}`;
    manualDniInput.value = "";
    manualDniError.textContent = "";
    manualDniPanel.classList.remove("d-none");
    manualDniInput.focus();
}

function closeManualDniDialog() {
    manualDniPanel.classList.add("d-none");
    if (phase === "scanning") {
        scanner.start();
    }
}

function askConfirm(message) {
    return new Promise(resolve => {
        const finish = accepted => {
            confirmPanel.classList.add("d-none");
            confirmAccept.removeEventListener("click", onAccept);
            confirmCancel.removeEventListener("click", onCancel);
            resolve(accepted);
        };
        const onAccept = () => finish(true);
        const onCancel = () => finish(false);
        confirmText.textContent = message;
        confirmAccept.addEventListener("click", onAccept);
        confirmCancel.addEventListener("click", onCancel);
        confirmPanel.classList.remove("d-none");
        confirmAccept.focus();
    });
}

setCount(0);
setRegisterButtonLabel(null, 0);
setPhase("select");

function setPhase(nextPhase) {
    phase = nextPhase;
    const visibility = [
        [cameraPanel, nextPhase === "select" || nextPhase === "scanning"],
        [mesaSelectControls, nextPhase === "select"],
        [mesaInfoView, nextPhase === "info"],
        [mesaInfoControls, nextPhase === "info"],
        [scanControls, nextPhase === "scanning"],
        [mesaSummaryView, nextPhase === "summary"]
    ];
    for (const [element, visible] of visibility) {
        element?.classList.toggle("d-none", !visible);
        element?.setAttribute("aria-hidden", visible ? "false" : "true");
    }
    registerButton.disabled = nextPhase !== "scanning";
}

function showMesaInfo(info, message = "") {
    mesaInfoCodigo.textContent = info.codigo;
    const lineas = [
        info.departamento ? `Departamento: ${info.departamento}` : null,
        info.claustro ? `Claustro: ${info.claustro}` : null,
        info.sede ? `Sede: ${info.sede}` : null,
        `Estado: ${info.estado_display}`,
        `Electores: ${info.electores} (${info.registrados} ya registrados)`
    ].filter(Boolean);
    mesaInfoDetalle.textContent = lineas.join("\n");
    mesaInfoMensaje.textContent = message;
    mesaStartButton.disabled = info.estado === "procesada";
    if (info.estado === "procesada") {
        mesaInfoMensaje.textContent = "Esta mesa ya fue procesada.";
    }
    setPhase("info");
}

function showMesaSummary(mesaCodigo, qrCount, sinInasistencias) {
    const qrLabel = qrCount === 1 ? "QR" : "QRs";
    const detalle = sinInasistencias
        ? "Sin inasistencias en esta mesa"
        : `${qrCount} ${qrLabel} unicos acumulados`;
    lastPageSummary.textContent = `Mesa ${mesaCodigo} procesada\n${detalle}`;
    setPhase("summary");
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
        setStatus(phase === "scanning" ? `Mesa ${mesaActual.codigo}: escaneá la hoja completa del padrón.` : "Escaneá el QR de la mesa.");
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

/* Consulta datos de la mesa (por QR o codigo escrito); el estado solo cambia al pulsar "Comenzar". */
async function consultarMesa(referencia) {
    if (isQueryingMesa) {
        return;
    }

    isQueryingMesa = true;
    scanner.stop();
    setStatus("Buscando mesa...", "info");

    try {
        const result = await gestionarMesa(app.dataset.mesaApiUrl, { accion: "consultar", ...referencia });
        mesaPendiente = { referencia, info: result.mesa };
        void playSuccessTone();
        showMesaInfo(result.mesa);
    }
    catch (error) {
        setStatus(error.message, "error");
        void playErrorTone();
        if (phase === "select") {
            scanner.start();
        }
    }
    finally {
        isQueryingMesa = false;
    }
}

async function comenzarEscaneoMesa() {
    if (!mesaPendiente || isSubmitting) {
        return;
    }

    isSubmitting = true;
    mesaStartButton.disabled = true;
    mesaInfoMensaje.textContent = "Iniciando mesa...";

    try {
        const result = await gestionarMesa(app.dataset.mesaApiUrl, { accion: "iniciar", ...mesaPendiente.referencia });
        mesaActual = result.mesa;
        mesaBaseRegistrados = result.mesa.registrados;
        mesaAccumulatedCodes.clear();
        scanner.clear();
        setCount(0);
        setRegisterButtonLabel(mesaActual.codigo, 0);
        setPhase("scanning");
        setStatus(`Mesa ${mesaActual.codigo}: escaneá la hoja completa del padrón.`);
        scanner.start();
    }
    catch (error) {
        mesaInfoMensaje.textContent = error.message;
        mesaStartButton.disabled = false;
        void playErrorTone();
    }
    finally {
        isSubmitting = false;
    }
}

function clearMesaState() {
    scanner.clear();
    mesaActual = null;
    mesaPendiente = null;
    mesaBaseRegistrados = 0;
    mesaAccumulatedCodes.clear();
    lastNoticeAt = 0;
    setCount(0);
    setRegisterButtonLabel(null, 0);
}

function clearCurrentPageScanOnly() {
    scanner.clear();
    const accumulatedCount = mesaAccumulatedCodes.size;
    setCount(accumulatedCount);
    setRegisterButtonLabel(mesaActual?.codigo, accumulatedCount);
}

/* Confirma la mesa en el servidor; sin QRs pide confirmar que no hubo inasistencias. */
async function finalizarMesa() {
    const sinRegistros = mesaBaseRegistrados + mesaAccumulatedCodes.size === 0;

    if (sinRegistros && !(await askConfirm(`No se escanearon QRs en la mesa ${mesaActual.codigo}.\n\nSe confirmará que en esta mesa no hubo inasistencias. ¿Continuar?`))) {
        scanner.start();
        return false;
    }

    try {
        await gestionarMesa(app.dataset.mesaApiUrl, {
            accion: "finalizar",
            codigo_mesa: mesaActual.codigo,
            confirmar_sin_inasistencias: sinRegistros
        });
    }
    catch (error) {
        setStatus(error.message, "error");
        void playErrorTone();
        scanner.start();
        return false;
    }

    void playSuccessTone();
    const total = mesaAccumulatedCodes.size;
    const codigo = mesaActual.codigo;
    clearMesaState();
    showMesaSummary(codigo, total, sinRegistros);
    return true;
}

async function registerCurrentPage(origin) {
    if (isSubmitting || phase !== "scanning") {
        return;
    }

    stopAutoRegisterTimer();

    if (scanner.codes.size === 0) {
        if (origin === "manual") {
            isSubmitting = true;
            scanner.stop();
            try {
                await finalizarMesa();
            }
            finally {
                isSubmitting = false;
            }
        }
        return;
    }

    const detectedCount = scanner.codes.size;

    isSubmitting = true;
    scanner.stop();
    setStatus("Registrando hoja...", "info");

    try {
        const result = await submitPage(
            app.dataset.apiUrl,
            scanner.codes,
            mesaActual.codigo
        );

        if (result.invalidos_otra_eleccion?.length) {
            throw new Error("Se detectaron QRs de otra elección. Verificá que la hoja corresponda a la elección activa.");
        }

        if (result.invalidos_otra_mesa?.length) {
            throw new Error(`Hay QRs de otra mesa. Registrá primero la mesa ${mesaActual.codigo}.`);
        }

        if (result.invalidos?.length) {
            throw new Error("Se detectaron QRs inválidos o que no corresponden a la mesa actual.");
        }

        setStatus(
            `Hoja registrada (${detectedCount} QR). Pasar a la siguiente.`,
            "success"
        );
        void playSuccessTone();

        for (const code of scanner.codes) {
            mesaAccumulatedCodes.add(code);
        }

        if (origin === "manual") {
            await finalizarMesa();
            return;
        }

        clearCurrentPageScanOnly();

        await sleep(NEXT_PAGE_COOLDOWN_MS);
        scanner.start();
    }
    catch (error) {
        setStatus(error.message, "error");
        void playErrorTone();
        scanner.start();

        const mesaVisibleCount = getProjectedUniqueMesaCount(scanner.codes);
        setCount(mesaVisibleCount);
        setRegisterButtonLabel(mesaActual?.codigo, mesaVisibleCount);
        restartAutoRegisterTimer();
    }
    finally {
        isSubmitting = false;
    }
}

function volverASeleccionDeMesa() {
    stopAutoRegisterTimer();
    clearMesaState();
    mesaInfoMensaje.textContent = "";
    setPhase("select");
    setStatus("Escaneá el QR de la mesa.");

    if (cameraStarted) {
        scanner.start();
    } else if (esDispositivoMovil) {
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

mesaStartButton.addEventListener("click", () => {
    void comenzarEscaneoMesa();
});

mesaChangeButton.addEventListener("click", volverASeleccionDeMesa);

mesaCodeForm.addEventListener("submit", event => {
    event.preventDefault();
    const codigo = mesaCodeInput.value.trim().toUpperCase();
    if (!codigo) {
        setStatus("Ingresá el código de mesa (CODIGO_DEPARTAMENTO-NUMERO_DE_MESA).", "error");
        return;
    }
    void consultarMesa({ codigo_mesa: codigo });
});

for (const button of manualLoadButtons) {
    button.addEventListener("click", () => {
        if (mesaActual && phase === "scanning") {
            openManualDniDialog();
        }
    });
}

manualDniCancel.addEventListener("click", closeManualDniDialog);

manualDniForm.addEventListener("submit", event => {
    event.preventDefault();
    const dni = manualDniInput.value.trim();
    if (!dni || !mesaActual) {
        manualDniError.textContent = "Ingresá un DNI válido.";
        return;
    }

    const submitButton = manualDniForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    manualDniError.textContent = "";

    void (async () => {
        try {
            const result = await submitManualAttendance(app.dataset.apiUrl, mesaActual.codigo, dni);

            if (result.invalidos?.length) {
                manualDniError.textContent = `No se encontró al elector en la mesa ${mesaActual.codigo}.`;
                void playErrorTone();
                return;
            }

            if (result.creados?.length) {
                mesaBaseRegistrados += 1;
                closeManualDniDialog();
                setStatus(`Inasistencia registrada en la mesa ${mesaActual.codigo}.`, "success");
                void playSuccessTone();
                return;
            }

            if (result.ya_registrados?.length) {
                closeManualDniDialog();
                setStatus(`El elector ya estaba registrado en la mesa ${mesaActual.codigo}.`, "info");
                return;
            }

            manualDniError.textContent = "No se pudo completar la carga manual.";
            void playErrorTone();
        } catch (error) {
            manualDniError.textContent = error.message;
            void playErrorTone();
        } finally {
            submitButton.disabled = false;
        }
    })();
});

resetSessionButton.addEventListener("click", volverASeleccionDeMesa);

if (manualDesktopForm) {
    manualDesktopForm.addEventListener("submit", event => {
        event.preventDefault();

        const formData = new FormData(manualDesktopForm);
        const mesaCodigo = String(formData.get("mesa_codigo") || "").trim().toUpperCase();
        const dni = String(formData.get("dni") || "").trim();
        const submitButton = manualDesktopForm.querySelector('button[type="submit"]');

        if (!mesaCodigo || !dni) {
            return;
        }

        void (async () => {
            submitButton.disabled = true;
            manualDesktopStatus.textContent = "Registrando inasistencia...";
            manualDesktopStatus.dataset.estado = "info";

            try {
                const result = await submitManualAttendance(manualDesktopForm.dataset.apiUrl, mesaCodigo, dni);
                if (result.invalidos?.length) {
                    manualDesktopStatus.textContent = `No se encontró al elector en la mesa ${mesaCodigo}.`;
                    manualDesktopStatus.dataset.estado = "error";
                } else if (result.creados?.length) {
                    manualDesktopStatus.textContent = `Inasistencia registrada en la mesa ${mesaCodigo}.`;
                    manualDesktopStatus.dataset.estado = "success";
                    manualDesktopForm.reset();
                    document.querySelector("#manual-mesa-codigo").focus();
                } else if (result.ya_registrados?.length) {
                    manualDesktopStatus.textContent = `El elector ya estaba registrado en la mesa ${mesaCodigo}.`;
                    manualDesktopStatus.dataset.estado = "info";
                } else {
                    manualDesktopStatus.textContent = "No se pudo completar la carga manual.";
                    manualDesktopStatus.dataset.estado = "error";
                }
            } catch (error) {
                manualDesktopStatus.textContent = error.message;
                manualDesktopStatus.dataset.estado = "error";
            } finally {
                submitButton.disabled = false;
            }
        })();
    });
}

if (esDispositivoMovil) {
    void startCamera();
}

document.addEventListener(
    "visibilitychange",
    () => {
        if (document.hidden) {
            stopAll();
        } else if (esDispositivoMovil) {
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
