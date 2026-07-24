# Escaneo QR — Voto UTN

Proyecto Django único y responsive para registrar asistencia desde hojas de padrón con QR. PC y celular consumen la misma aplicación; las vistas administrativas se resuelven con Django Admin y la operación de mesa está optimizada para móvil.

## Arquitectura

```
config/                 configuración y rutas del proyecto
apps/elections/         entidad Elección y selección de mesa
apps/attendance/        modelo, caso de uso y API de asistencia
templates/              vistas Django responsivas
static/js/              módulos ES6: camera, scanner, attendance, api y ui
```

La vista no conoce la persistencia: `AttendanceBatchAPIView` valida la petición y delega el caso de uso a `AttendanceService`. El modelo impone unicidad por elección/código, que protege también ante dos dispositivos concurrentes. La cámara, el procesamiento QR y la UI están desacoplados en módulos ES6.

El lector toma frames continuamente y analiza las 20 celdas (4 × 5) de la hoja con ZXing-JS. Los textos detectados se conservan en un `Set`, por lo que una lectura repetida no duplica la asistencia. Al confirmar una página se envía un lote al endpoint REST protegido por sesión y CSRF.

## Inicio local (Windows / PowerShell)

1. Instalar Python **3.12** y PostgreSQL. Crear una base llamada `escaneo_qr`.
2. Desde esta carpeta crear el entorno e instalar dependencias:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Ajustar las credenciales PostgreSQL en `.env`, migrar y crear el administrador:

   ```powershell
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver 0.0.0.0:8000
   ```

4. Abrir `http://127.0.0.1:8000/admin/`, crear una Elección habilitada y luego acceder con el usuario creado a `http://127.0.0.1:8000/`.

Para usar la cámara desde el teléfono, ambos equipos deben estar en la misma red Wi‑Fi. `getUserMedia` exige **HTTPS** cuando la página no es `localhost`; el servidor HTTP básico sólo sirve para probar desde la PC. Para desarrollo móvil, generá un certificado local confiable con [mkcert](https://github.com/FiloSottile/mkcert) y ejecutá:

```powershell
mkcert -install
mkcert 192.168.1.45 localhost 127.0.0.1  # reemplazar por la IP de tu PC
python manage.py runserver_plus 0.0.0.0:8000 --cert-file 192.168.1.45+2.pem --key-file 192.168.1.45+2-key.pem
```

Instalá también la CA generada por mkcert en el teléfono, y abrí `https://IP_DE_TU_PC:8000/`. Agregá esa IP a `DJANGO_ALLOWED_HOSTS` en `.env`.

> El contenido del QR se trata como el identificador único de votante. En producción conviene firmar el payload QR o validarlo contra el padrón institucional antes de permitir el registro.
