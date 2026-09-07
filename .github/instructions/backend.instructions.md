---
applyTo: "VotoUTN/apps/**/*.py,VotoUTN/config/**/*.py"
---

# Backend Django

- Utilizar nombres de dominio en español.
- No traducir APIs estándar de Django/Python.
- Mantener lógica compleja fuera de las vistas.
- Utilizar transacciones en operaciones críticas.
- Aplicar restricciones de base de datos.
- Justificar `PROTECT`, `CASCADE`, `SET_NULL` u otra estrategia.
- No eliminar datos mediante migraciones sin plan.
- Aplicar permisos en backend.
- Agregar pruebas para las reglas modificadas.
- Consultar `docs/modelo_dominio.md` y `docs/decisiones_funcionales.md`.
