---
applyTo: "VotoUTN/apps/asistencia/**,VotoUTN/static/js/**,VotoUTN/templates/asistencia/**"
---

# Asistencia y QR

- Preservar el funcionamiento existente del escáner.
- La interfaz mobile es la misma aplicación web responsive abierta desde navegador.
- Validar todos los QR nuevamente en servidor.
- No confiar en valores enviados por JavaScript.
- La autoridad de mesa no registra participación.
- El administrativo de junta registra participación.
- Usar una clave de QR separada de `SECRET_KEY`.
- No considerar Base64 como cifrado.
- Verificar el mecanismo criptográfico real antes de afirmar que un dato está cifrado.
- El objetivo funcional es sustituir legajo por DNI antes de aplicar la protección criptográfica.
- No exponer DNI en claro.
- Incluir pruebas de regresión.
