---
applyTo: "VotoUTN/**/tests/**,VotoUTN/**/*test*.py"
---

# Pruebas

- Cada regla crítica debe tener prueba positiva y negativa.
- Cada error corregido debe incluir prueba de regresión cuando corresponda.
- No depender de servicios externos reales.
- Simular Keycloak y proveedores de correo.
- Probar restricciones de unicidad en base de datos.
- Probar permisos desde backend.
- Probar que `K-001` y `E-001` no puedan coexistir en la misma elección.
- Probar herencia/restricción de sedes en cascada.
- Probar QR válido, inválido, manipulado, de otra elección, de otra mesa y duplicado.
