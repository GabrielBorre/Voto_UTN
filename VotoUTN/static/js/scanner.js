import { BrowserQRCodeReader } from "https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/+esm";

export class PageQrScanner {

    reader = new BrowserQRCodeReader();
    codes = new Set();
    running = false;
    busy = false;
    useNativeDetector = false;
    nativeDetector = null;

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

            if (this.useNativeDetector) {
                // El detector nativo puede leer directamente del tag video y detectar MÚLTIPLES QRs
                const barcodes = await this.nativeDetector.detect(this.video);
                for (const barcode of barcodes) {
                    this.#processText(barcode.rawValue);
                }
            } else {
                // Fallback con ZXing corrigiendo la relación de aspecto del Canvas
                if (this.canvas.width !== width || this.canvas.height !== height) {
                    this.canvas.width = width;
                    this.canvas.height = height;
                }
                await this.decodeRegion(0, 0, width, height);
            }

            this.onStatus?.(`QR detectados: ${this.codes.size}/15`);
        } catch {
            // Ignorar errores de lectura en frames individuales
        } finally {
            this.busy = false;
        }
    }

    async decodeRegion(x, y, w, h) {
        this.ctx.drawImage(this.video, x, y, w, h, 0, 0, this.canvas.width, this.canvas.height);
        try {
            const result = await this.reader.decodeFromCanvas(this.canvas);
            this.#processText(result?.getText());
        } catch {
            // No se detectó QR en este frame con ZXing
        }
    }

    #processText(text) {
        const cleaned = text?.trim();
        if (!cleaned || this.codes.has(cleaned)) return;
        this.codes.add(cleaned);
        this.onCode?.(cleaned, this.codes.size);
    }
}