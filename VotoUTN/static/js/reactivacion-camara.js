export const ESPERA_SIN_NUEVOS_MS = 1200;
export const INTERVALO_REENFOQUE_MS = 2500;
export const AUSENCIA_HOJA_MS = 1000;
export const MAXIMO_REENFOQUES = 2;

/*
 * Si la hoja sigue a la vista pero no aparecen QR nuevos, pide reenfoques puntuales,
 * que reproducen el efecto de mover levemente la hoja. Un QR nuevo reinicia los intentos.
 */
export class ReactivadorCamara {
    #intervalo = null;
    #ultimoNuevoAt = 0;
    #presenciaDesdeAt = null;
    #ultimoReenfoqueAt = -Infinity;
    #intentos = 0;
    #disponible = true;
    #ocupado = false;

    constructor(camara, escaner, estaActivo, ahora = () => performance.now()) {
        this.camara = camara;
        this.escaner = escaner;
        this.estaActivo = estaActivo;
        this.ahora = ahora;
    }

    iniciar() {
        if (this.#intervalo !== null) return;
        this.notificarCodigoNuevo();
        this.#intervalo = window.setInterval(() => void this.revisar(), 300);
    }

    detener() {
        window.clearInterval(this.#intervalo);
        this.#intervalo = null;
    }

    notificarCodigoNuevo() {
        this.#ultimoNuevoAt = this.ahora();
        this.#intentos = 0;
    }

    async revisar() {
        if (this.#ocupado || !this.#disponible || !this.estaActivo()) return;
        const ahora = this.ahora();
        if (ahora - this.escaner.ultimaDeteccionAt > AUSENCIA_HOJA_MS) {
            this.#presenciaDesdeAt = null;
            return;
        }
        this.#presenciaDesdeAt ??= ahora;
        const desde = Math.max(this.#ultimoNuevoAt, this.#presenciaDesdeAt);
        if (ahora - desde < ESPERA_SIN_NUEVOS_MS || ahora - this.#ultimoReenfoqueAt < INTERVALO_REENFOQUE_MS) return;
        if (this.#intentos >= MAXIMO_REENFOQUES) return;

        this.#ocupado = true;
        this.#ultimoReenfoqueAt = ahora;
        this.#intentos++;
        try {
            this.#disponible = await this.camara.reenfocar();
        } catch (error) {
            console.warn("No se pudo reenfocar la cámara; se conserva el enfoque continuo.", error);
            this.#disponible = false;
        } finally {
            this.#ocupado = false;
        }
    }
}
