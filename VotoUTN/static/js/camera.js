export class Camera {

    stream = null;
    track = null;
    capabilities = {};
    settings = {};

    constructor(video) {
        this.video = video;
    }

    async start() {

        if (!window.isSecureContext) {
            throw new Error(
                "La cámara requiere HTTPS. Abrí la aplicación mediante https://IP_DE_TU_PC:8000."
            );
        }

        if (!navigator.mediaDevices?.getUserMedia) {
            throw new Error(
                "Este navegador no soporta acceso a la cámara."
            );
        }

        const profiles = [
            {
                video: {
                    facingMode: { ideal: "environment" },
                    width: { ideal: 1280 }, // Priorizar 720p para mayor velocidad de procesamiento FPS[cite: 1]
                    height: { ideal: 720 }
                },
                audio: false
            },
            {
                video: {
                    facingMode: { ideal: "environment" },
                    width: { ideal: 1920 },
                    height: { ideal: 1080 }
                },
                audio: false
            },
            {
                video: {
                    facingMode: { ideal: "environment" }
                },
                audio: false
            }
        ];
        
        let lastError = null;

        for (const profile of profiles) {

            try {

                this.stream = await navigator.mediaDevices.getUserMedia(profile);

                break;

            } catch (error) {

                lastError = error;

            }

        }

        if (!this.stream) {

            const messages = {
                NotAllowedError:
                    "Permiso de cámara denegado.",

                NotFoundError:
                    "No se encontró ninguna cámara.",

                NotReadableError:
                    "La cámara está siendo utilizada por otra aplicación.",

                OverconstrainedError:
                    "No fue posible obtener una resolución compatible."
            };

            throw new Error(
                messages[lastError?.name] ??
                "No fue posible abrir la cámara."
            );

        }

        this.track = this.stream.getVideoTracks()[0];

        this.capabilities =
            this.track.getCapabilities?.() ?? {};

        this.settings =
            this.track.getSettings?.() ?? {};

        await this.#configureCamera();

        this.video.srcObject = this.stream;

        this.video.playsInline = true;

        this.video.muted = true;

        await this.video.play();

    }

    async #configureCamera() {

        if (!this.track.applyConstraints) return;

        const advanced = [];

        if (this.capabilities.focusMode?.includes?.("continuous")) {

            advanced.push({
                focusMode: "continuous"
            });

        }

        if (advanced.length === 0) return;

        try {

            await this.track.applyConstraints({
                advanced
            });

        }
        catch {

            // Algunos dispositivos ignoran estas opciones.
            // No afecta el funcionamiento.

        }

    }

    stop() {

        this.stream
            ?.getTracks()
            .forEach(track => track.stop());

        this.stream = null;
        this.track = null;
        this.capabilities = {};
        this.settings = {};

    }

}
