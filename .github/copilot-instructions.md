# Instrucciones generales de Voto UTN

Antes de cambios importantes, consultar:

- `docs/prompt_maestro.md`
- `docs/decisiones_funcionales.md`
- `docs/modelo_dominio.md`
- `docs/plan_implementacion.md`

## Stack

- Python 3.12
- Django 5.2 LTS
- PostgreSQL
- Django REST Framework
- Django Templates
- Bootstrap 5
- JavaScript ES6 modular

## Reglas

- Modificar el repositorio existente.
- No crear un proyecto paralelo.
- Mantener el dominio en español.
- No eliminar migraciones existentes.
- Crear migraciones seguras.
- No borrar datos para resolver problemas de esquema.
- No modificar contratos de API sin actualizar consumidores.
- Incluir pruebas para reglas críticas.
- No incluir secretos ni certificados privados.
- Preservar el comportamiento del QR.
- No asumir que Base64 es cifrado.
- Validar criptográficamente JWT de Keycloak.
- Aplicar autorización en backend.
- La autoridad de mesa no registra participación.
- El administrativo de junta registra participación.
- Usar `EleccionClaustroDepartamento`, no `DivisionElectoral`.
