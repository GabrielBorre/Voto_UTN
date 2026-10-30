# Escaneo QR — Voto UTN

Proyecto Django único y responsive para registrar asistencia desde hojas de padrón con QR. PC y celular consumen la misma aplicación; las vistas administrativas se resuelven con Django Admin y la operación de mesa está optimizada para móvil.

## Arquitectura

```
config/                 configuración y rutas del proyecto
apps/elecciones/         entidad Elección y selección de mesa
apps/asistencia/        modelo, caso de uso y API de asistencia
templates/              vistas Django responsivas
static/js/              módulos ES6: camera, scanner, asistencia, api y ui
```

La vista no conoce la persistencia: `AttendanceBatchAPIView` valida la petición y delega el caso de uso a `AttendanceService`. El modelo impone unicidad por elección/código, que protege también ante dos dispositivos concurrentes. La cámara, el procesamiento QR y la UI están desacoplados en módulos ES6.

El lector alterna la detección múltiple de la imagen completa con `BarcodeDetector`,
cuando está disponible, y un barrido complementario con ZXing. El barrido se ejecuta
aunque el detector nativo repita siempre los mismos códigos, sin requerir movimiento
de la hoja. Con ZXing, que devuelve un QR por lectura, alterna la imagen completa
con 30 bandas verticalmente solapadas, de arriba hacia abajo, sin deformar los
recortes. Si el detector nativo falla, se informa en consola y se continúa con
ZXing. Así puede acumular los 15 QR de una hoja fija, incluidos
los extremos. Los textos detectados se conservan en un `Set`, por lo que una lectura
repetida no duplica la asistencia. Al confirmar una página se envía un lote al
endpoint REST protegido por sesión y CSRF.

### Cámara y alineación de la hoja

- Se solicita cámara trasera en Full HD, adaptada a la orientación inicial del
  teléfono, con perfiles alternativos de 720p y resolución predeterminada.
  Son preferencias: el navegador decide la resolución efectiva.
- Se solicita enfoque continuo solamente si la cámara lo declara compatible.
  Si el ajuste falla, se informa en la consola y se conserva el enfoque del equipo.
- La vista muestra el encuadre completo, sin recortar sus extremos. La referencia
  superior central permite alinear «Comprobante de emisión de voto». Deben quedar
  visibles también el primer y el último QR.
- El barrido de regiones es **digital**, no un barrido óptico de enfoque.
  `pointsOfInterest` y `focusDistance` dependen del navegador y del hardware; no
  permiten garantizar un barrido vertical de autofocus en todos los celulares.
  No se fuerza enfoque manual ni zoom, que podrían empeorar la lectura.
- Leer los 15 QR sin mover el teléfono requiere papel plano, cámara paralela,
  distancia suficiente para encuadrar toda la columna, iluminación uniforme y
  nitidez. No se puede garantizar esa lectura en todo dispositivo: debe probarse
  con el teléfono y la hoja impresa reales.

Referencia técnica: [Media Capture Image, W3C](https://w3c.github.io/mediacapture-image/).

### Regresión del lector en navegador

Desde esta carpeta, ejecutar `python -m http.server 8876 --bind 127.0.0.1` y abrir
`http://127.0.0.1:8876/tests/frontend/escaner.html`. Requiere acceso al CDN de ZXing,
igual que el escáner de producción. No solicita acceso a la cámara real.

La prueba decodifica una imagen sintética fija de 1080 × 1920 con 15 QR únicos
(`tests/frontend/hoja_15_qr.png`), comprueba ambos extremos, deduplicación, cobertura
de las bandas, detección múltiple nativa simulada (incluido un detector estancado
en los mismos 10 QR y otro que falla) y perfiles/enfoque de cámara simulados.
El tiempo informado corresponde al equipo de prueba, no garantiza el
rendimiento ni la nitidez de una cámara real.

## Inicio local (Windows / PowerShell)

1. Instalar Python **3.12** y PostgreSQL. Crear una base llamada `voto_utn`.
2. Desde esta carpeta crear el entorno e instalar dependencias:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Ajustar las credenciales PostgreSQL en `.env`, migrar y crear el administrador:

   ```powershell
   python manage.py makemigrations
   python manage.py migrate
   python manage.py seed_demo_data
   python manage.py createsuperuser
   python manage.py runserver 0.0.0.0:8000
   ```

   `seed_demo_data` es el comando único para preparar un entorno de trabajo compartido: carga los
   parámetros institucionales estándar y una elección demostrativa idempotente con los cuatro
   claustros, puestos, listas y candidaturas de ejemplo. Si solamente se necesitan los catálogos,
   puede ejecutarse `python manage.py cargar_parametros_estandar`.

4. Abrir `http://127.0.0.1:8000/admin/`, crear una Elección habilitada y luego acceder con el usuario creado a `http://127.0.0.1:8000/`.

Para usar la cámara desde el teléfono, ambos equipos deben estar en la misma red Wi‑Fi. `getUserMedia` exige **HTTPS** cuando la página no es `localhost`; el servidor HTTP básico sólo sirve para probar desde la PC. Para desarrollo móvil, generá un certificado local confiable con [mkcert](https://github.com/FiloSottile/mkcert) y ejecutá:

```powershell
mkcert -install
mkcert 192.168.1.45 localhost 127.0.0.1  # reemplazar por la IP de tu PC
python manage.py runserver_plus 0.0.0.0:8000 --cert-file 192.168.1.45+2.pem --key-file 192.168.1.45+2-key.pem
```

Instalá también la CA generada por mkcert en el teléfono, y abrí `https://192.168.1.45:8000/`. Agregá esa IP a `DJANGO_ALLOWED_HOSTS` en `.env`.

> El comando `seed_voters` genera payloads opacos firmados a partir del padrón. La primera emisión queda registrada y bloquea cambios automáticos de padrón o mesa que invalidarían los QR impresos.

## Acceso por HTTPS con Docker (PC y celular, sin mkcert)

Con `docker compose up -d` el stack levanta además `proxy` (Caddy), que expone:

- `http://localhost:8000/` → redirige a HTTPS.
- `https://localhost:8443/` desde la PC.
- `https://<IP-de-tu-PC-en-la-Wi-Fi>:8443/` desde el celular (misma red Wi-Fi).

Caddy firma el certificado al vuelo con su propia CA local (`tls internal` + `on_demand`), para
cualquier host o IP con el que se lo llame, sin generar ni instalar nada manualmente. El navegador
va a mostrar una advertencia de certificado no confiable la primera vez (es autofirmado); hay que
aceptarla/continuar una sola vez por dispositivo. Eso ya alcanza para que `getUserMedia` (la cámara)
funcione, porque la conexión es HTTPS real.



python manage.py seed_voters --election-id 1 --configuracion-departamento-id 2

docker compose exec web python manage.py seed_demo_data
docker compose exec web python manage.py seed_keycloak_demo
