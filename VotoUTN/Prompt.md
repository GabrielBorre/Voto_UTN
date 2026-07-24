Quiero desarrollar un sistema de gestión electoral universitario utilizando Python + Django.

La solución estará compuesta por UNA ÚNICA aplicación web responsive que será utilizada tanto desde computadoras como desde teléfonos móviles.

NO quiero desarrollar una aplicación Android ni utilizar Flutter, Kotlin o React.

La aplicación deberá adaptarse automáticamente al dispositivo.

Stack tecnológico:

Backend
- Python 3.12
- Django 5
- Django REST Framework
- PostgreSQL

Frontend
- Django Templates
- HTML5
- CSS3
- JavaScript ES6
- Bootstrap 5
- HTMX (para interacciones simples sin recargar la página)

Escaneo QR
- ZXing-JS
- MediaDevices API (navigator.mediaDevices.getUserMedia)

Objetivo:
El sistema será responsive.
Desde PC se utilizarán todas las funcionalidades administrativas.
Desde celular únicamente se utilizarán las funciones necesarias para el escaneo del padrón.
No deben existir dos aplicaciones separadas.
Todo debe formar parte del mismo proyecto Django.

FUNCIONALIDAD DE ESCANEO:
Flujo:
1. Seleccionar elección
2. Abrir cámara
3. Escanear una hoja del padrón
4. Detectar automáticamente TODOS los QR visibles (20 QR por hoja)
5. Mostrar cantidad de QR encontrados y Boton para escanear la siguiente pagina
6. Registrar asistencia en Django
No se debe escanear QR por QR.
Debe procesarse el video continuamente utilizando ZXing-JS.
Mientras la cámara está abierta:
- analizar frames continuamente
- detectar múltiples QR
- mantener un Set para evitar duplicados
- actualizar la interfaz en tiempo real
La cámara debe ocupar casi toda la pantalla del celular.


INTERFAZ MOBILE:
Debe verse como una aplicación nativa.
Utilizar:
Bootstrap 5
Diseño limpio
Material Design
Botones grandes
Tipografía legible
Optimizada para uso con una mano.
Pantallas:
1 Login
2 Selección de elección
3 Escaneo QR
4 Procesando
5 Resultado

JAVASCRIPT:
No utilizar jQuery.
Utilizar únicamente JavaScript moderno (ES6).
Organizar el código en módulos.
Separar:
camera.js
scanner.js
attendance.js
api.js
ui.js

RESPONSIVE:
Detectar automáticamente cuando el usuario accede desde un celular.
En ese caso:
- menú simplificado
- botones grandes
- navegación vertical
- cámara en pantalla completa


OBJETIVO DEL CÓDIGO:
Generar una base profesional, mantenible y escalable.
Priorizar:
- Clean Architecture
- separación de responsabilidades
- reutilización
- buenas prácticas Django
- código desacoplado
No generar código monolítico.
Antes de escribir código, proponer la estructura completa del proyecto y justificar las decisiones arquitectónicas.

Solo desarrollar la funcionalidad de escaneo de qrs, con todo lo necesario para poder levantar la aplicacion utilizando mi computadora como servidor en la carpeta EscaneoQR