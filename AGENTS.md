# Instrucciones para agentes de desarrollo

## Documentación obligatoria

Antes de analizar o modificar el repositorio, leer:

1. `docs/prompt_maestro.md`
2. `docs/decisiones_funcionales.md`
3. `docs/modelo_dominio.md`
4. `docs/plan_implementacion.md`

## Forma de trabajo

- Trabajar sobre el proyecto existente.
- No crear un proyecto Django paralelo.
- Ejecutar una sola etapa o subetapa por tarea, salvo instrucción expresa.
- Antes de modificar archivos, identificar dependencias y consumidores.
- No eliminar migraciones existentes.
- Toda modificación del modelo debe incluir una migración segura.
- Toda corrección de una regla crítica debe incluir pruebas.
- Informar qué archivos se crean, modifican o eliminan.
- Ejecutar verificaciones y pruebas antes de considerar terminada una tarea.
- No declarar una tarea completa si existen pruebas fallidas, imports rotos o migraciones pendientes.

## Stack

- Python 3.12
- Django 5.2 LTS
- PostgreSQL
- Django REST Framework
- Django Templates
- Bootstrap 5
- JavaScript ES6 modular

## Reglas críticas

- No utilizar React, Vue, Angular, Flutter, Kotlin ni SQLite.
- Utilizar español consistente para el dominio.
- No incluir secretos ni credenciales.
- La aplicación de asistencia es web responsive y se usa desde navegador móvil.
- La autoridad de mesa no registra participación.
- El registro de participación es responsabilidad del administrativo de junta.
- Preservar el comportamiento funcional del QR existente.
- Validar criptográficamente los JWT de Keycloak.
- Consultar `docs/decisiones_funcionales.md` antes de reinterpretar una regla confirmada.

## Verificación mínima

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate --plan
python manage.py test
```

No ejecutar comandos destructivos sin autorización expresa.
