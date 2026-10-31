import { BrowserQRCodeReader } from "https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/+esm";

const CANTIDAD_BANDAS = 30;
// Cada vuelta cambia el muestreo como lo haría un leve movimiento de la hoja o del celular.
const VARIANTES_BARRIDO = [
    { divisorAlto: 12, escala: 1 },
    { divisorAlto: 9, escala: 0.75 },
    { divisorAlto: 16, escala: 1.5 }
];
const CANTIDAD_VENTANAS_NATIVAS = 5;
const ALTO_VENTANA_NATIVA = 0.3;

export class PageQrScanner {

    reader = new BrowserQRCodeReader();
    codes = new Set();
    running = false;
    busy = false;
    useNativeDetector = false;
    nativeDetector = null;
    lastReportedCount = 0;
    indiceRegion = 0;
    indiceVariante = 0;
    indiceVentanaNativa = 0;
    turnoDetectorNativo = true;
    ultimaDeteccionAt = 0;

    constructor(video, canvas, onCode, onStatus) {
        this.video = video;
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d", { willReadFrequently: true });
        this.onCode = onCode;
        this.onStatus = onStatus;

        // Verificar soporte nativo de BarcodeDetector (Mucho más rápido en móviles)
        if ("BarcodeDetector" in window) {
            try {
                this.nativeDetector = new BarcodeDetector({ formats: ["qr_code"] });
                this.useNativeDetector = true;
            } catch (e) {
                this.useNativeDetector = false;
            }
        }
    }

    start() {
        if (this.running) return;
        this.running = true;
        this.loop();
    }

    stop() {
        this.running = false;
        this.reader.reset?.();
    }

    clear() {
        this.codes.clear();
        this.lastReportedCount = 0;
        this.indiceRegion = 0;
        this.indiceVariante = 0;
        this.indiceVentanaNativa = 0;
        this.turnoDetectorNativo = true;
    }

    async loop() {
        while (this.running) {
            if (this.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && !this.busy) {
                await this.scanFrame();
            }
            await new Promise(resolve => requestAnimationFrame(resolve));
        }
    }

    async scanFrame() {
        this.busy = true;
        try {
            const width = this.video.videoWidth;
            const height = this.video.videoHeight;

            if (!width || !height) return;

            if (this.useNativeDetector && this.turnoDetectorNativo) {
                this.turnoDetectorNativo = false;
                try {
                    const barcodes = await this.#detectarNativo(width, height);
                    for (const barcode of barcodes) {
                        this.#processText(barcode.rawValue);
                    }
                } catch (error) {
                    console.warn("El detector nativo falló; se continúa el barrido con ZXing.", error);
                    this.useNativeDetector = false;
                }
            } else {
                // Complementar el detector nativo aunque repita siempre los mismos QR.
                const variante = VARIANTES_BARRIDO[this.indiceVariante];
                if (this.indiceRegion === 0) {
                    await this.decodeRegion(0, 0, width, height, Math.min(variante.escala, 1));
                } else {
                    const alto = Math.ceil(height / variante.divisorAlto);
                    const y = Math.round((height - alto) * (this.indiceRegion - 1) / (CANTIDAD_BANDAS - 1));
                    await this.decodeRegion(0, y, width, alto, variante.escala);
                }
                this.indiceRegion = (this.indiceRegion + 1) % (CANTIDAD_BANDAS + 1);
                if (this.indiceRegion === 0) {
                    this.indiceVariante = (this.indiceVariante + 1) % VARIANTES_BARRIDO.length;
                }
                this.turnoDetectorNativo = true;
            }

            if (this.codes.size !== this.lastReportedCount) {
                this.lastReportedCount = this.codes.size;
                this.onStatus?.(
                    `QR detectados: ${this.codes.size}/15`,
                    { emphasis: "large", durationMs: 2000 }
                );
            }
        } catch {
            // Ignorar errores de lectura en frames individuales
        } finally {
            this.busy = false;
        }
    }

    async decodeRegion(x, y, w, h, escala = 1) {
        this.#dibujarRegion(x, y, w, h, escala);
        try {
            const result = await this.reader.decodeFromCanvas(this.canvas);
            this.#processText(result?.getText());
        } catch {
            // No se detectó QR en este frame con ZXing
        }
    }

    /* Alterna el cuadro completo con ventanas superpuestas, que agrandan los QR pequeños. */
    async #detectarNativo(width, height) {
        const ventana = this.indiceVentanaNativa;
        this.indiceVentanaNativa = (ventana + 1) % (CANTIDAD_VENTANAS_NATIVAS + 1);
        if (ventana === 0) {
            return this.nativeDetector.detect(this.video);
        }
        const alto = Math.round(height * ALTO_VENTANA_NATIVA);
        const y = Math.round((height - alto) * (ventana - 1) / (CANTIDAD_VENTANAS_NATIVAS - 1));
        this.#dibujarRegion(0, y, width, alto, 1);
        return this.nativeDetector.detect(this.canvas);
    }

    #dibujarRegion(x, y, w, h, escala) {
        const ancho = Math.round(w * escala);
        const alto = Math.round(h * escala);
        if (this.canvas.width !== ancho || this.canvas.height !== alto) {
            this.canvas.width = ancho;
            this.canvas.height = alto;
        }
        this.ctx.drawImage(this.video, x, y, w, h, 0, 0, ancho, alto);
    }

    #processText(text) {
        const cleaned = text?.trim();
        if (!cleaned) return;
        this.ultimaDeteccionAt = performance.now();
        if (this.codes.has(cleaned)) return;
        this.codes.add(cleaned);
        this.onCode?.(cleaned, this.codes.size);
    }
}